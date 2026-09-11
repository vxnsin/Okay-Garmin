"""The voice engine: wake word -> command capture -> transcription -> action.

Emits events (state changes, microphone level, transcripts) that the settings
window and the desktop overlay both subscribe to.
"""

from __future__ import annotations

import threading
import time
import winsound
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from . import actions
from . import config as config_module
from . import models
from .logging_setup import get_logger
from .paths import sounds_dir
from .spotify import SpotifyClient, SpotifyError
from .stt import matching
from .stt.audio import AudioSource, rms_level
from .version import WAKE_WORD

log = get_logger("engine")

# Seconds of silence that end a command, and how long we wait for any speech
# at all before deciding the wake word was a false positive.
SILENCE_TO_END = 0.8
NO_SPEECH_TIMEOUT = 2.5
SPEECH_LEVEL = 0.06
MIN_CAPTURE_BYTES = 9600  # 0.3 s of 16 kHz mono int16
LEVEL_EVENT_INTERVAL = 0.05  # throttle to ~20/s so the JS bridge keeps up

STATE_STARTING = "starting"
STATE_DOWNLOADING = "downloading"
STATE_LISTENING = "listening"
STATE_ARMED = "armed"
STATE_RECORDING = "recording"
STATE_TRANSCRIBING = "transcribing"
STATE_EXECUTING = "executing"
STATE_PAUSED = "paused"
STATE_ERROR = "error"


@dataclass
class _Capture:
    mode: str  # "wake" or "ptt"
    buffer: bytearray = field(default_factory=bytearray)
    started_at: float = field(default_factory=time.monotonic)
    last_voice_at: float | None = None


class VoiceEngine:
    def __init__(self) -> None:
        self._listeners: list[Callable[[dict[str, Any]], None]] = []
        self._stop = threading.Event()
        self._paused = threading.Event()
        self._ptt_down = threading.Event()
        self._thread: threading.Thread | None = None

        self.spotify = SpotifyClient()
        self._audio: AudioSource | None = None
        self._wake = None
        self._transcriber = None
        self._capture: _Capture | None = None

        self.state = STATE_STARTING
        self.last_error: str | None = None
        self.history: list[dict[str, Any]] = []
        self._last_level_event = 0.0
        self._last_trigger = 0.0
        self._reload_requested = threading.Event()

    # ------------------------------------------------------------------ events

    def subscribe(self, listener: Callable[[dict[str, Any]], None]) -> None:
        self._listeners.append(listener)

    def emit(self, event: dict[str, Any]) -> None:
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception:
                log.exception("Event listener failed")

    def _set_state(self, state: str, **extra: Any) -> None:
        self.state = state
        self.emit({"type": "state", "state": state, **extra})

    def _log_history(self, entry: dict[str, Any]) -> None:
        entry["at"] = time.time()
        self.history.append(entry)
        del self.history[:-30]
        self.emit({"type": "transcript", **entry})

    # ------------------------------------------------------------------ control

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="voice-engine", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._audio:
            self._audio.stop()

    def set_paused(self, paused: bool) -> None:
        if paused:
            self._paused.set()
            self._capture = None
            self._set_state(STATE_PAUSED)
        else:
            self._paused.clear()
            self._set_state(STATE_LISTENING)

    @property
    def paused(self) -> bool:
        return self._paused.is_set()

    def request_reload(self) -> None:
        """Pick up a changed recognition language or microphone."""
        self._reload_requested.set()

    def ptt_press(self) -> None:
        if not self._paused.is_set():
            self._ptt_down.set()

    def ptt_release(self) -> None:
        self._ptt_down.clear()

    def status(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "paused": self.paused,
            "error": self.last_error,
            "history": self.history[-15:],
        }

    # ------------------------------------------------------------------ sounds

    def _play(self, filename: str) -> None:
        if not config_module.get("sound_enabled", True):
            return
        path = sounds_dir() / filename
        if not path.is_file():
            log.debug("Sound missing: %s", path)
            return
        try:
            winsound.PlaySound(str(path), winsound.SND_ASYNC | winsound.SND_FILENAME)
        except Exception as exc:
            log.warning("Could not play %s: %s", filename, exc)

    # ------------------------------------------------------------------ setup

    def _load_models(self) -> bool:
        cfg = config_module.get_config()
        language = cfg["stt"]["language"]
        size = cfg["stt"]["whisper_model"]

        status = models.download_status(language, size)
        if not (status["vosk"]["available"] and status["whisper"]["available"]):
            self._set_state(STATE_DOWNLOADING)

            def progress(stage: str, fraction: float, message: str) -> None:
                self.emit(
                    {
                        "type": "model_progress",
                        "stage": stage,
                        "progress": fraction,
                        "message": message,
                    }
                )

            try:
                models.ensure_all(language, size, progress)
            except Exception as exc:
                self.last_error = f"Model download failed: {exc}"
                log.error(self.last_error)
                self._set_state(STATE_ERROR, error=self.last_error)
                return False

        model_path = models.vosk_model_path(language)
        if model_path is None:
            self.last_error = f"No wake-word model for language '{language}'"
            self._set_state(STATE_ERROR, error=self.last_error)
            return False

        from .stt.command_whisper import CommandTranscriber
        from .stt.wake_vosk import WakeWordDetector

        try:
            self._wake = WakeWordDetector(str(model_path), WAKE_WORD)
        except Exception as exc:
            self.last_error = f"Wake-word model failed to load: {exc}"
            self._set_state(STATE_ERROR, error=self.last_error)
            return False

        # Whisper takes a second or two to load. Do it in the background so the
        # wake word is already live; the first command just waits if it isn't.
        def load_whisper() -> None:
            try:
                self._transcriber = CommandTranscriber(
                    size=size,
                    language=language,
                    compute_type=cfg["stt"]["compute_type"],
                )
            except Exception as exc:
                self.last_error = f"Whisper failed to load: {exc}"
                log.error(self.last_error)
                self.emit({"type": "state", "state": STATE_ERROR, "error": self.last_error})

        threading.Thread(target=load_whisper, name="whisper-load", daemon=True).start()
        return True

    # ------------------------------------------------------------------ main loop

    def _run(self) -> None:
        while not self._stop.is_set():
            self._reload_requested.clear()
            if not self._load_models():
                return
            try:
                self._listen_loop()
            except Exception as exc:
                self.last_error = str(exc)
                log.exception("Voice loop crashed")
                self._set_state(STATE_ERROR, error=str(exc))
                time.sleep(3)
            finally:
                if self._audio:
                    self._audio.stop()
                    self._audio = None

    def _listen_loop(self) -> None:
        cfg = config_module.get_config()
        self._audio = AudioSource(device=cfg.get("input_device"))
        self._audio.start()
        self._set_state(STATE_LISTENING if not self.paused else STATE_PAUSED)

        while not self._stop.is_set() and not self._reload_requested.is_set():
            block = self._audio.read(timeout=0.5)
            if block is None:
                continue

            level = rms_level(block)
            now = time.monotonic()
            if now - self._last_level_event >= LEVEL_EVENT_INTERVAL:
                self._last_level_event = now
                self.emit({"type": "level", "level": round(level, 3)})

            if self._paused.is_set():
                continue

            # Push-to-talk wins over the wake word.
            if self._ptt_down.is_set() and self._capture is None:
                self._begin_capture("ptt")
            if self._capture is not None:
                self._continue_capture(block, level, now)
                continue

            detected, _text = self._wake.accept(block)
            if detected:
                if now - self._last_trigger < float(cfg.get("cooldown", 2.0)):
                    continue
                self._last_trigger = now
                self._play("trigger.wav")
                self.emit({"type": "wake"})
                self._begin_capture("wake")

    def _begin_capture(self, mode: str) -> None:
        self._capture = _Capture(mode=mode)
        self._set_state(STATE_ARMED if mode == "wake" else STATE_RECORDING, mode=mode)

    def _continue_capture(self, block: bytes, level: float, now: float) -> None:
        capture = self._capture
        if capture is None:
            return

        capture.buffer.extend(block)
        if level >= SPEECH_LEVEL:
            if capture.last_voice_at is None:
                self._set_state(STATE_RECORDING, mode=capture.mode)
            capture.last_voice_at = now

        elapsed = now - capture.started_at
        timeout = float(config_module.get("command_timeout", 6.0))

        if capture.mode == "ptt":
            # Push-to-talk ends when the key comes back up, with a hard cap so a
            # stuck key cannot record forever.
            if not self._ptt_down.is_set() or elapsed > timeout * 2:
                self._finish_capture()
            return

        if capture.last_voice_at is None:
            if elapsed > NO_SPEECH_TIMEOUT:
                log.debug("Wake word fired but nothing followed -- standing down")
                self._abort_capture()
            return

        if now - capture.last_voice_at >= SILENCE_TO_END or elapsed > timeout:
            self._finish_capture()

    def _abort_capture(self) -> None:
        self._capture = None
        if self._wake is not None:
            self._wake.reset()
        self._set_state(STATE_LISTENING if not self.paused else STATE_PAUSED)

    def _finish_capture(self) -> None:
        capture = self._capture
        self._capture = None
        if capture is None:
            return

        pcm = bytes(capture.buffer)
        if len(pcm) < MIN_CAPTURE_BYTES:
            self._abort_capture()
            return

        self._set_state(STATE_TRANSCRIBING)
        if self._transcriber is None:
            log.info("Whisper still loading -- waiting")
            for _ in range(100):
                if self._transcriber is not None or self._stop.is_set():
                    break
                time.sleep(0.1)
        if self._transcriber is None:
            self._log_history(
                {"text": "", "matched": None, "score": 0.0, "error": "whisper-unavailable"}
            )
            self._abort_capture()
            return

        text = self._transcriber.transcribe(pcm)
        self._handle_text(text)

        if self._wake is not None:
            self._wake.reset()
        if self._audio is not None:
            self._audio.drain()
        self._set_state(STATE_LISTENING if not self.paused else STATE_PAUSED)

    def _handle_text(self, text: str) -> None:
        if not text.strip():
            self._log_history({"text": "", "matched": None, "score": 0.0})
            return

        cfg = config_module.get_config()
        command, score, argument = matching.best_command(
            text, cfg.get("voice_commands", []), float(cfg.get("match_threshold", 0.72))
        )

        self._log_history(
            {
                "text": text,
                "matched": command.get("command") if command else None,
                "score": round(score, 2),
                "argument": argument,
            }
        )

        if command is None:
            log.info("No command matched %r (best %.2f)", text, score)
            return

        self._play("action.wav")
        self._set_state(STATE_EXECUTING, command=command.get("command"))
        self.run_command(command, argument)

    def run_command(self, command: dict, argument: str = "") -> None:
        """Execute a command off the audio thread so a delay cannot stall capture.

        Spotify calls also belong off this thread: a search plus a play request
        is two network round trips, and blocking here would drop audio.
        """

        def worker() -> None:
            try:
                if command.get("type") == "spotify":
                    ok = self._run_spotify(command, argument)
                else:
                    ok = actions.execute(command)
                self.emit({"type": "executed", "command": command.get("command"), "ok": ok})
            except Exception:
                log.exception("Command execution failed")

        threading.Thread(target=worker, name="command-exec", daemon=True).start()

    # Actions that take the free text of a {} slot.
    SPOTIFY_NEEDS_ARGUMENT = {"play", "queue"}

    # Actions that change the track, so the HUD should show the new one.
    SPOTIFY_CHANGES_TRACK = {"next", "previous", "resume"}

    def _run_spotify(self, command: dict, argument: str) -> bool:
        """Run a Spotify command and push the result to the HUD.

        Every branch produces an optional track plus a `note` naming what
        happened, so the HUD can caption "shuffle on" rather than always
        claiming something started playing.
        """
        action = (command.get("value") or "play").strip()

        delay = float(command.get("delay") or 0)
        if delay > 0:
            time.sleep(delay)

        if action in self.SPOTIFY_NEEDS_ARGUMENT and not argument:
            log.info("Spotify %r command had nothing to search for", action)
            self.emit({"type": "spotify_error", "error": "nothing-said"})
            return False

        try:
            track, note = self._spotify_action(action, argument)
        except SpotifyError as exc:
            log.warning("Spotify: %s", exc)
            self.emit({"type": "spotify_error", "error": str(exc)})
            return False

        if track or note:
            self.emit({"type": "now_playing", "note": note, **(track or {})})
        return True

    def _spotify_action(self, action: str, argument: str):
        """Returns (track, note). Either may be None."""
        spotify = self.spotify

        if action == "play":
            return spotify.play(argument), "playing"
        if action == "queue":
            return spotify.enqueue(argument), "queued"
        if action == "current":
            return spotify.now_playing(), "current"

        if action == "shuffle_on":
            spotify.set_shuffle(True)
            return spotify.now_playing(), "shuffle_on"
        if action == "shuffle_off":
            spotify.set_shuffle(False)
            return spotify.now_playing(), "shuffle_off"
        if action == "shuffle_toggle":
            enabled = spotify.toggle_shuffle()
            return spotify.now_playing(), "shuffle_on" if enabled else "shuffle_off"

        if action == "repeat_track":
            spotify.set_repeat("track")
            return spotify.now_playing(), "repeat_track"
        if action == "repeat_all":
            spotify.set_repeat("context")
            return spotify.now_playing(), "repeat_all"
        if action == "repeat_off":
            spotify.set_repeat("off")
            return spotify.now_playing(), "repeat_off"
        if action == "repeat_cycle":
            mode = spotify.cycle_repeat()
            note = {"off": "repeat_off", "context": "repeat_all", "track": "repeat_track"}[mode]
            return spotify.now_playing(), note

        if action == "like":
            return spotify.set_saved(True), "liked"
        if action == "unlike":
            return spotify.set_saved(False), "unliked"
        if action == "like_toggle":
            track, saved = spotify.toggle_saved()
            return track, "liked" if saved else "unliked"

        if action in ("volume_up", "volume_down"):
            volume = spotify.nudge_volume(10 if action == "volume_up" else -10)
            track = spotify.now_playing() or {}
            return {**track, "volume": volume}, "volume"

        # pause / resume / next / previous
        spotify.control(action)
        if action in self.SPOTIFY_CHANGES_TRACK:
            # Give Spotify a moment to switch before asking what is playing.
            time.sleep(0.6)
            return spotify.now_playing(), "playing"
        return None, action
