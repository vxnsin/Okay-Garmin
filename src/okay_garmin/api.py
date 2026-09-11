"""The object exposed to the settings window as window.pywebview.api."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import webbrowser
from typing import Any

from . import autostart
from . import config as config_module
from . import models
from .logging_setup import get_logger
from .paths import app_dir, is_frozen, log_dir, web_dir
from .spotify import SpotifyError
from .stt.audio import list_input_devices
from .updater.core import check_for_update
from .version import GITHUB_URL, WAKE_WORD, __version__

log = get_logger("api")


class Api:
    def __init__(self, app) -> None:
        self._app = app

    # ------------------------------------------------------------------ config

    def get_config(self) -> dict[str, Any]:
        return config_module.get_config()

    def save_config(self, new_config: dict) -> dict[str, Any]:
        previous = config_module.get_config()
        saved = config_module.set_config(new_config)

        # Only these need the engine to restart; everything else is read live.
        restart_keys = [
            ("input_device",),
            ("stt", "language"),
            ("stt", "whisper_model"),
            ("stt", "compute_type"),
        ]
        needs_reload = any(
            _dig(previous, path) != _dig(saved, path) for path in restart_keys
        )
        if needs_reload:
            log.info("Voice settings changed -- reloading engine")
            self._app.engine.request_reload()

        self._app.ptt.configure(
            saved["push_to_talk"]["enabled"], saved["push_to_talk"]["hotkey"]
        )
        geometry_keys = [
            ("overlay", "position"),
            ("overlay", "scale"),
            ("overlay", "custom"),
        ]
        if any(_dig(previous, path) != _dig(saved, path) for path in geometry_keys):
            self._app.overlay.reposition()
        if previous.get("ui_language") != saved.get("ui_language"):
            self._app.overlay.send_labels()
            self._app.tray.refresh()

        return {"status": "ok"}

    def get_translations(self) -> dict[str, Any]:
        """Bundled UI strings.

        The page is loaded from file://, where fetch() is blocked, so the
        translations come across the bridge instead of being fetched by JS.
        """
        result: dict[str, Any] = {}
        i18n_dir = web_dir() / "i18n"
        if i18n_dir.is_dir():
            for path in i18n_dir.glob("*.json"):
                try:
                    result[path.stem] = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError) as exc:
                    log.warning("Could not read %s: %s", path.name, exc)
        return result

    # ------------------------------------------------------------------ system

    def get_autostart(self) -> bool:
        return autostart.is_enabled()

    def set_autostart(self, enable: bool) -> dict[str, Any]:
        actual = autostart.set_enabled(bool(enable))
        return {
            "status": "ok",
            "enabled": actual,
            # From source there is no sensible executable to register.
            "supported": is_frozen(),
        }

    def pick_path(self, type_: str) -> str | None:
        """Native file/folder picker, run on the UI window."""
        window = self._app.window
        if window is None:
            return None

        import webview

        try:
            if type_ == "folder":
                result = window.create_file_dialog(webview.FOLDER_DIALOG)
            elif type_ == "run":
                result = window.create_file_dialog(
                    webview.OPEN_DIALOG,
                    file_types=("Programs (*.exe;*.bat;*.cmd;*.lnk)", "All files (*.*)"),
                )
            else:
                result = window.create_file_dialog(webview.OPEN_DIALOG)
        except Exception as exc:
            log.error("File dialog failed: %s", exc)
            return None

        if not result:
            return None
        return result[0] if isinstance(result, (list, tuple)) else result

    def get_devices(self) -> list[dict[str, Any]]:
        return list_input_devices()

    def open_external(self, url: str) -> dict[str, Any]:
        # target="_blank" does nothing inside the embedded browser.
        if not url.startswith(("http://", "https://")):
            return {"status": "error", "reason": "unsupported-scheme"}
        webbrowser.open(url)
        return {"status": "ok"}

    def open_logs(self) -> dict[str, Any]:
        os.startfile(str(log_dir()))
        return {"status": "ok"}

    def open_config_folder(self) -> dict[str, Any]:
        os.startfile(str(config_module.config_path().parent))
        return {"status": "ok"}

    # ------------------------------------------------------------------ engine

    def get_status(self) -> dict[str, Any]:
        return self._app.engine.status()

    def set_paused(self, paused: bool) -> dict[str, Any]:
        self._app.engine.set_paused(bool(paused))
        return {"status": "ok", "paused": self._app.engine.paused}

    def test_command(self, index: int) -> dict[str, Any]:
        """Run a configured command from the UI, without speaking."""
        commands = config_module.get("voice_commands", [])
        if not 0 <= index < len(commands):
            return {"status": "error", "reason": "out-of-range"}
        self._app.engine.run_command(commands[index])
        return {"status": "ok"}

    # ------------------------------------------------------------------ models

    def get_models_status(self) -> dict[str, Any]:
        cfg = config_module.get_config()
        return models.download_status(cfg["stt"]["language"], cfg["stt"]["whisper_model"])

    def download_models(self) -> dict[str, Any]:
        cfg = config_module.get_config()

        def worker() -> None:
            def progress(stage: str, fraction: float, message: str) -> None:
                self._app.broadcast(
                    {
                        "type": "model_progress",
                        "stage": stage,
                        "progress": fraction,
                        "message": message,
                    }
                )

            try:
                models.ensure_all(
                    cfg["stt"]["language"], cfg["stt"]["whisper_model"], progress
                )
                self._app.broadcast({"type": "models_ready"})
                self._app.engine.request_reload()
            except Exception as exc:
                log.error("Model download failed: %s", exc)
                self._app.broadcast({"type": "model_error", "error": str(exc)})

        threading.Thread(target=worker, name="model-download", daemon=True).start()
        return {"status": "started"}

    # ------------------------------------------------------------------ updates

    def get_version(self) -> dict[str, Any]:
        info = check_for_update()
        info["repo"] = GITHUB_URL
        return info

    def run_updater(self) -> dict[str, Any]:
        if is_frozen():
            updater = app_dir() / "update.exe"
            if not updater.is_file():
                return {"status": "error", "reason": "updater-missing"}
            command = [str(updater)]
        else:
            command = [sys.executable, "-m", "okay_garmin.updater"]

        try:
            subprocess.Popen(command, close_fds=True)
        except OSError as exc:
            log.error("Could not start the updater: %s", exc)
            return {"status": "error", "reason": str(exc)}

        # The updater signals us to quit once it has verified the download,
        # so we don't tear ourselves down here.
        return {"status": "ok"}

    def get_app_info(self) -> dict[str, Any]:
        return {
            "version": f"v{__version__}",
            # Fixed, not a setting -- the UI shows it but cannot change it.
            "wake_word": WAKE_WORD,
            "repo": GITHUB_URL,
            "frozen": is_frozen(),
            "config_path": str(config_module.config_path()),
            "log_path": str(log_dir()),
        }

    # ------------------------------------------------------------------ spotify

    def get_spotify_status(self) -> dict[str, Any]:
        status = self._app.engine.spotify.status()
        status["configured"] = bool(config_module.get("spotify.client_id", "").strip())
        status["redirect_uri"] = "http://127.0.0.1:8888/callback"
        return status

    def connect_spotify(self) -> dict[str, Any]:
        """Run the PKCE flow in the background; the browser does the talking."""
        client_id = config_module.get("spotify.client_id", "").strip()
        if not client_id:
            return {"status": "error", "reason": "no-client-id"}

        def worker() -> None:
            try:
                self._app.engine.spotify.authorize(client_id)
                self._app.broadcast({"type": "spotify_connected"})
            except SpotifyError as exc:
                log.warning("Spotify authorisation failed: %s", exc)
                self._app.broadcast({"type": "spotify_auth_error", "error": str(exc)})
            except Exception as exc:
                log.exception("Spotify authorisation crashed")
                self._app.broadcast({"type": "spotify_auth_error", "error": str(exc)})

        threading.Thread(target=worker, name="spotify-auth", daemon=True).start()
        return {"status": "started"}

    def disconnect_spotify(self) -> dict[str, Any]:
        self._app.engine.spotify.disconnect()
        return {"status": "ok"}

    # ------------------------------------------------------------------ overlay

    def start_overlay_placement(self) -> dict[str, Any]:
        return self._app.overlay.start_placement()

    def end_overlay_placement(self) -> dict[str, Any]:
        return self._app.overlay.end_placement()

    def preview_overlay(self) -> dict[str, Any]:
        """Flash a sample card so scale and position can be judged."""
        overlay = self._app.overlay
        overlay.show()
        overlay.handle_event(
            {
                "type": "now_playing",
                "title": "Bohemian Rhapsody",
                "subtitle": "Queen",
                "kind": "track",
                "image": None,
            }
        )
        overlay.hide(after=3.5)
        return {"status": "ok"}

    # ------------------------------------------------------------------ window

    def hide_window(self) -> dict[str, Any]:
        self._app.hide_settings()
        return {"status": "ok"}

    def quit_app(self) -> dict[str, Any]:
        self._app.quit()
        return {"status": "ok"}


def _dig(data: dict, path: tuple[str, ...]) -> Any:
    node: Any = data
    for part in path:
        if not isinstance(node, dict):
            return None
        node = node.get(part)
    return node
