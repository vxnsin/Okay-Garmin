"""Executing what a matched command asks for."""

from __future__ import annotations

import os
import subprocess
import threading
import time
from pathlib import Path

from pynput import keyboard

from .logging_setup import get_logger

log = get_logger("actions")

MODIFIERS = {
    "ctrl": keyboard.Key.ctrl,
    "control": keyboard.Key.ctrl,
    "alt": keyboard.Key.alt,
    "shift": keyboard.Key.shift,
    "win": keyboard.Key.cmd,
    "windows": keyboard.Key.cmd,
    "cmd": keyboard.Key.cmd,
}

# v1 only handled single characters and F-keys, so a command bound to Enter or
# Media Play silently did nothing.
NAMED_KEYS = {
    "enter": keyboard.Key.enter,
    "return": keyboard.Key.enter,
    "space": keyboard.Key.space,
    "tab": keyboard.Key.tab,
    "esc": keyboard.Key.esc,
    "escape": keyboard.Key.esc,
    "backspace": keyboard.Key.backspace,
    "delete": keyboard.Key.delete,
    "insert": keyboard.Key.insert,
    "home": keyboard.Key.home,
    "end": keyboard.Key.end,
    "pageup": keyboard.Key.page_up,
    "pagedown": keyboard.Key.page_down,
    "up": keyboard.Key.up,
    "down": keyboard.Key.down,
    "left": keyboard.Key.left,
    "right": keyboard.Key.right,
    "printscreen": keyboard.Key.print_screen,
    "capslock": keyboard.Key.caps_lock,
    "mediaplay": keyboard.Key.media_play_pause,
    "medianext": keyboard.Key.media_next,
    "mediaprev": keyboard.Key.media_previous,
    "volumeup": keyboard.Key.media_volume_up,
    "volumedown": keyboard.Key.media_volume_down,
    "mute": keyboard.Key.media_volume_mute,
}

# Set while we synthesise key presses. Push-to-talk checks it, otherwise a
# command bound to the push-to-talk combination would retrigger itself.
synthetic_input = threading.Event()

_controller = keyboard.Controller()


def parse_key(token: str):
    token = token.strip().lower()
    if token in NAMED_KEYS:
        return NAMED_KEYS[token]
    if len(token) > 1 and token[0] == "f" and token[1:].isdigit():
        number = int(token[1:])
        if 1 <= number <= 20:
            return getattr(keyboard.Key, f"f{number}")
    if len(token) == 1:
        return token
    return None


def parse_hotkey(combo: str) -> tuple[list, object | None]:
    """Split "ctrl+shift+f8" into ([Key.ctrl, Key.shift], Key.f8)."""
    modifiers = []
    main = None
    for token in combo.lower().split("+"):
        token = token.strip()
        if not token:
            continue
        if token in MODIFIERS:
            key = MODIFIERS[token]
            if key not in modifiers:
                modifiers.append(key)
        elif main is None:
            main = parse_key(token)
    return modifiers, main


def press_hotkey(combo: str) -> bool:
    modifiers, main = parse_hotkey(combo)
    if main is None and not modifiers:
        log.warning("Hotkey %r could not be parsed", combo)
        return False

    synthetic_input.set()
    try:
        for modifier in modifiers:
            _controller.press(modifier)
        if main is not None:
            _controller.press(main)
            _controller.release(main)
        for modifier in reversed(modifiers):
            _controller.release(modifier)
        return True
    except Exception as exc:
        log.error("Could not send hotkey %r: %s", combo, exc)
        # Never leave a modifier stuck down -- that would wedge the whole desktop.
        for modifier in reversed(modifiers):
            try:
                _controller.release(modifier)
            except Exception:
                pass
        return False
    finally:
        # Give the target application a moment to consume the keystroke before
        # we start listening to our own synthetic events again.
        threading.Timer(0.3, synthetic_input.clear).start()


# Media keys work with any player that listens to them -- Spotify, VLC,
# YouTube in a browser -- so they are the fallback for people who do not
# connect a Spotify account.
MEDIA_ACTIONS = {
    "play_pause": "mediaplay",
    "next": "medianext",
    "previous": "mediaprev",
    "volume_up": "volumeup",
    "volume_down": "volumedown",
    "mute": "mute",
}


def press_media(action: str) -> bool:
    key = MEDIA_ACTIONS.get(action)
    if key is None:
        log.warning("Unknown media action %r", action)
        return False
    return press_hotkey(key)


def open_path(path_value: str) -> bool:
    path = Path(path_value)
    if not path.exists():
        log.warning("Path does not exist: %s", path_value)
        return False
    try:
        if path.suffix.lower() in {".bat", ".cmd"}:
            subprocess.Popen(["cmd", "/c", str(path)], shell=False)
        else:
            os.startfile(str(path))
        return True
    except OSError as exc:
        log.error("Could not open %s: %s", path_value, exc)
        return False


def execute(command: dict) -> bool:
    """Run a configured command. Returns whether it did something."""
    delay = float(command.get("delay") or 0)
    if delay > 0:
        log.info("Waiting %.1fs before executing %r", delay, command.get("command"))
        time.sleep(delay)

    kind = command.get("type", "hotkey")
    value = (command.get("value") or "").strip()
    if not value:
        log.warning("Command %r has no value", command.get("command"))
        return False

    if kind == "hotkey":
        return press_hotkey(value)
    if kind == "media":
        return press_media(value)
    if kind in {"file", "folder", "run"}:
        return open_path(value)

    log.warning("Unknown command type %r", kind)
    return False
