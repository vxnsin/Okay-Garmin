"""Push-to-talk: hold a global hotkey, speak, release.

An alternative to the wake word for noisy rooms or voice chat, where saying
"Okay Garmin" out loud is awkward.

pynput's GlobalHotKeys only fires on press, so this tracks key state itself in
order to detect the release too.
"""

from __future__ import annotations

from collections.abc import Callable

from pynput import keyboard

from . import actions
from .logging_setup import get_logger

log = get_logger("ptt")

_CANONICAL = {
    keyboard.Key.ctrl: "ctrl",
    keyboard.Key.ctrl_l: "ctrl",
    keyboard.Key.ctrl_r: "ctrl",
    keyboard.Key.alt: "alt",
    keyboard.Key.alt_l: "alt",
    keyboard.Key.alt_r: "alt",
    keyboard.Key.alt_gr: "alt",
    keyboard.Key.shift: "shift",
    keyboard.Key.shift_l: "shift",
    keyboard.Key.shift_r: "shift",
    keyboard.Key.cmd: "windows",
    keyboard.Key.cmd_l: "windows",
    keyboard.Key.cmd_r: "windows",
}


def _canonical(key) -> str | None:
    if key in _CANONICAL:
        return _CANONICAL[key]
    if isinstance(key, keyboard.KeyCode):
        if key.char:
            return key.char.lower()
        return None
    name = getattr(key, "name", None)
    return name.lower() if name else None


def _parse(combo: str) -> set[str]:
    aliases = {"control": "ctrl", "win": "windows", "cmd": "windows", "return": "enter"}
    parts = set()
    for token in combo.lower().split("+"):
        token = token.strip()
        if token:
            parts.add(aliases.get(token, token))
    return parts


class PushToTalk:
    def __init__(self, on_press: Callable[[], None], on_release: Callable[[], None]) -> None:
        self._on_press = on_press
        self._on_release = on_release
        self._required: set[str] = set()
        self._down: set[str] = set()
        self._active = False
        self._enabled = False
        self._listener: keyboard.Listener | None = None

    def configure(self, enabled: bool, hotkey: str) -> None:
        self._enabled = enabled
        self._required = _parse(hotkey) if hotkey else set()
        if self._active and not enabled:
            self._active = False
            self._on_release()
        log.info("Push-to-talk %s (%s)", "enabled" if enabled else "disabled", hotkey)

    def start(self) -> None:
        if self._listener is not None:
            return
        self._listener = keyboard.Listener(
            on_press=self._handle_press, on_release=self._handle_release
        )
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        if self._listener is not None:
            self._listener.stop()
            self._listener = None

    def _handle_press(self, key) -> None:
        # Ignore keystrokes we generated ourselves, otherwise a command bound to
        # the push-to-talk combination would retrigger push-to-talk.
        if actions.synthetic_input.is_set():
            return
        name = _canonical(key)
        if name is None:
            return
        self._down.add(name)

        if (
            self._enabled
            and self._required
            and not self._active
            and self._required.issubset(self._down)
        ):
            self._active = True
            log.debug("Push-to-talk engaged")
            self._on_press()

    def _handle_release(self, key) -> None:
        name = _canonical(key)
        if name is None:
            return
        self._down.discard(name)

        if self._active and not self._required.issubset(self._down):
            self._active = False
            log.debug("Push-to-talk released")
            self._on_release()
