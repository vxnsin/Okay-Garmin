"""The desktop HUD.

A small frameless window that appears when the wake word fires, shows a live
waveform, whatever was recognised, and -- for Spotify commands -- the cover,
title and artist of what started playing. It is click-through and never takes
focus, so it cannot interrupt what you were doing.

Visibility, placement and shape go through Win32 rather than pywebview:

  * pywebview's `hidden` is not honoured for secondary windows here, and its
    show()/hide() must not be called from the UI thread's own event handlers --
    they wait on that same thread. ShowWindow() is safe from anywhere.
  * `transparent=True` has no effect under the WebView2 backend; the window
    paints an opaque rectangle. Instead the window is given a rounded region,
    so the card has real rounded corners without needing alpha.

In placement mode the window becomes clickable and draggable so the user can
put it wherever they like; the HUD page calls back through OverlayApi.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any

import win32api
import win32con
import win32gui

from . import config as config_module
from .logging_setup import get_logger
from .paths import web_dir

log = get_logger("overlay")

BASE_WIDTH = 430
BASE_HEIGHT = 118
MARGIN = 48
TASKBAR_ALLOWANCE = 40
CORNER_RADIUS = 22
MIN_SCALE = 0.7
MAX_SCALE = 2.0

# Styles that make the HUD ignore the mouse and refuse focus. WS_EX_TOOLWINDOW
# also keeps it out of Alt+Tab.
_PASSIVE = (
    win32con.WS_EX_TRANSPARENT
    | win32con.WS_EX_NOACTIVATE
    | win32con.WS_EX_TOOLWINDOW
)

# States that reveal the HUD -- anything else lets it disappear.
_VISIBLE_STATES = {"armed", "recording", "transcribing", "executing"}


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _screen() -> tuple[int, int]:
    return (
        win32api.GetSystemMetrics(win32con.SM_CXSCREEN),
        win32api.GetSystemMetrics(win32con.SM_CYSCREEN),
    )


class OverlayApi:
    """Exposed to the HUD page so it can drag its own window."""

    def __init__(self, overlay: Overlay) -> None:
        self._overlay = overlay

    def drag(self, dx: float, dy: float) -> dict[str, Any]:
        return self._overlay.nudge(int(dx), int(dy))

    def placement_done(self) -> dict[str, Any]:
        self._overlay.end_placement()
        return {"status": "ok"}


class Overlay:
    """Wraps the HUD window. Safe to use even when the user turned it off."""

    TITLE = "Okay-Garmin HUD"

    def __init__(self, on_placement_end=None) -> None:
        self.window = None
        self._hwnd: int | None = None
        self._visible = False
        self._placing = False
        self._hide_timer: threading.Timer | None = None
        self._ready = threading.Event()
        self._on_placement_end = on_placement_end

    # ------------------------------------------------------------------ geometry

    def size(self) -> tuple[int, int]:
        scale = _clamp(float(config_module.get("overlay.scale", 1.0)), MIN_SCALE, MAX_SCALE)
        return int(BASE_WIDTH * scale), int(BASE_HEIGHT * scale)

    def position(self) -> tuple[int, int]:
        """Where the HUD should sit: a hand-placed point, or a preset corner."""
        width, height = self.size()
        screen_w, screen_h = _screen()

        if config_module.get("overlay.custom", False):
            x = config_module.get("overlay.x")
            y = config_module.get("overlay.y")
            if x is not None and y is not None:
                # Keep it on screen even if the resolution changed since.
                return (
                    int(_clamp(x, 0, max(0, screen_w - width))),
                    int(_clamp(y, 0, max(0, screen_h - height))),
                )

        placement = config_module.get("overlay.position", "bottom-center")
        vertical, _, horizontal = placement.partition("-")

        if horizontal == "left":
            x = MARGIN
        elif horizontal == "right":
            x = screen_w - width - MARGIN
        else:
            x = (screen_w - width) // 2

        y = MARGIN if vertical == "top" else screen_h - height - MARGIN - TASKBAR_ALLOWANCE
        return int(x), int(y)

    # ------------------------------------------------------------------ lifecycle

    def create(self):
        import webview

        width, height = self.size()
        x, y = self.position()

        self.window = webview.create_window(
            self.TITLE,
            str(web_dir() / "overlay.html"),
            js_api=OverlayApi(self),
            width=width,
            height=height,
            x=x,
            y=y,
            frameless=True,
            easy_drag=False,
            on_top=True,
            resizable=False,
            hidden=True,
        )
        self.window.events.loaded += self._on_loaded
        return self.window

    def _on_loaded(self) -> None:
        self._ready.set()
        # Off the UI thread: this both waits for the handle and calls ShowWindow.
        threading.Thread(target=self._prepare_window, daemon=True).start()

    def _prepare_window(self) -> None:
        for _ in range(60):
            hwnd = win32gui.FindWindow(None, self.TITLE)
            if hwnd:
                self._hwnd = hwnd
                break
            time.sleep(0.1)
        else:
            log.warning("HUD window handle not found -- it may capture clicks")
            return

        self._set_passive(True)
        self.apply_geometry()
        # pywebview's `hidden` is not honoured for this window, so hide it here.
        self._hide_now()
        self.send_labels()
        self._push({"type": "scale", "scale": config_module.get("overlay.scale", 1.0)})
        log.debug("HUD ready")

    def _set_passive(self, passive: bool) -> None:
        """Click-through while in use; clickable while being placed."""
        if self._hwnd is None:
            return
        try:
            style = win32gui.GetWindowLong(self._hwnd, win32con.GWL_EXSTYLE)
            style = (style | _PASSIVE) if passive else (style & ~_PASSIVE) | win32con.WS_EX_TOOLWINDOW
            win32gui.SetWindowLong(self._hwnd, win32con.GWL_EXSTYLE, style)
        except Exception as exc:
            log.warning("Could not change HUD input handling: %s", exc)

    def apply_geometry(self) -> None:
        """Move and resize the window, then re-round it."""
        if self._hwnd is None:
            return
        width, height = self.size()
        x, y = self.position()
        try:
            flags = win32con.SWP_NOACTIVATE | win32con.SWP_NOZORDER
            if not self._visible:
                flags |= win32con.SWP_NOREDRAW
            win32gui.SetWindowPos(self._hwnd, 0, x, y, width, height, flags)
        except Exception as exc:
            log.debug("Could not place the HUD: %s", exc)
        self._round_corners()

    def _round_corners(self) -> None:
        """Round the window itself.

        Measured from the real window rect rather than the configured size:
        the process is DPI-unaware, so Windows hands us a smaller physical
        window than we asked for, and a region built from our own numbers
        would push the lower-right corner outside the window.
        """
        if self._hwnd is None:
            return
        try:
            left, top, right, bottom = win32gui.GetWindowRect(self._hwnd)
            region = win32gui.CreateRoundRectRgn(
                0, 0, right - left + 1, bottom - top + 1, CORNER_RADIUS * 2, CORNER_RADIUS * 2
            )
            win32gui.SetWindowRgn(self._hwnd, region, True)
        except Exception as exc:
            log.debug("Could not round the HUD corners: %s", exc)

    def reposition(self) -> None:
        self.apply_geometry()
        self._push({"type": "scale", "scale": config_module.get("overlay.scale", 1.0)})

    # ------------------------------------------------------------------ placement

    def start_placement(self) -> dict[str, Any]:
        """Show the HUD with a sample card so the user can drag it into place."""
        if self._hwnd is None:
            return {"status": "error", "reason": "not-ready"}

        self._placing = True
        self._cancel_hide()
        self._set_passive(False)
        self.apply_geometry()
        self._push({"type": "placement", "active": True})
        self.show(activate=True)
        log.info("HUD placement mode on")
        return {"status": "ok"}

    def end_placement(self) -> dict[str, Any]:
        if not self._placing:
            return {"status": "ok"}

        self._placing = False
        self._push({"type": "placement", "active": False})
        self._set_passive(True)
        self._hide_now()
        log.info("HUD placement mode off")
        if self._on_placement_end is not None:
            try:
                self._on_placement_end()
            except Exception:
                log.exception("Placement callback failed")
        return {"status": "ok"}

    @property
    def placing(self) -> bool:
        return self._placing

    def nudge(self, dx: int, dy: int) -> dict[str, Any]:
        """Move the window by a delta and remember where it ended up."""
        if self._hwnd is None or not self._placing:
            return {"status": "error"}

        try:
            left, top, right, bottom = win32gui.GetWindowRect(self._hwnd)
        except Exception:
            return {"status": "error"}

        width, height = right - left, bottom - top
        screen_w, screen_h = _screen()
        x = int(_clamp(left + dx, 0, max(0, screen_w - width)))
        y = int(_clamp(top + dy, 0, max(0, screen_h - height)))

        try:
            win32gui.SetWindowPos(
                self._hwnd, 0, x, y, 0, 0,
                win32con.SWP_NOSIZE | win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE,
            )
        except Exception as exc:
            log.debug("Could not move the HUD: %s", exc)
            return {"status": "error"}

        config = config_module.get_config()
        config["overlay"].update({"custom": True, "x": x, "y": y})
        config_module.set_config(config)
        return {"status": "ok", "x": x, "y": y}

    # ------------------------------------------------------------------ visibility

    def _cancel_hide(self) -> None:
        if self._hide_timer is not None:
            self._hide_timer.cancel()
            self._hide_timer = None

    def show(self, activate: bool = False) -> None:
        self._cancel_hide()
        if self._hwnd is None or self._visible:
            return
        try:
            # SHOWNOACTIVATE keeps focus where it is, which matters for a HUD
            # that pops up while the user is typing somewhere else.
            win32gui.ShowWindow(
                self._hwnd,
                win32con.SW_SHOW if activate else win32con.SW_SHOWNOACTIVATE,
            )
            win32gui.SetWindowPos(
                self._hwnd, win32con.HWND_TOPMOST, 0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE | win32con.SWP_NOACTIVATE,
            )
            self._visible = True
        except Exception as exc:
            log.debug("Could not show the HUD: %s", exc)

    def hide(self, after: float = 0.0) -> None:
        if self._placing:
            return  # never hide out from under someone positioning it
        self._cancel_hide()
        if after <= 0:
            self._hide_now()
            return
        self._hide_timer = threading.Timer(after, self._hide_now)
        self._hide_timer.daemon = True
        self._hide_timer.start()

    def _hide_now(self) -> None:
        if self._hwnd is None or self._placing:
            return
        try:
            win32gui.ShowWindow(self._hwnd, win32con.SW_HIDE)
        except Exception as exc:
            log.debug("Could not hide the HUD: %s", exc)
        self._visible = False

    # ------------------------------------------------------------------ events

    def handle_event(self, event: dict[str, Any]) -> None:
        """Mirror engine events into the HUD, showing and hiding as needed."""
        if self.window is None:
            return
        if self._placing:
            return  # placement mode owns the window's contents

        if not config_module.get("overlay.enabled", True):
            if self._visible:
                self.hide()
            return

        kind = event.get("type")
        hide_after = float(config_module.get("overlay.hide_after", 2.5))

        if kind == "state":
            if event.get("state") in _VISIBLE_STATES:
                self.show()
            elif self._visible:
                self.hide(after=hide_after)
        elif kind == "wake":
            self.show()
        elif kind == "now_playing":
            # Worth a longer look than a plain command: there is artwork to see.
            self.show()
            self.hide(after=hide_after * 2.5)
        elif kind == "level" and not self._visible:
            # No point forwarding 20 level events a second to a hidden window.
            return

        self._push(event)

    def send_labels(self) -> None:
        """Push the HUD's captions in the user's interface language."""
        language = config_module.get("ui_language", "de")
        path = web_dir() / "i18n" / f"{language}.json"
        if not path.is_file():
            path = web_dir() / "i18n" / "en.json"

        try:
            strings = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            log.warning("Could not read HUD labels: %s", exc)
            return

        labels = {
            state: strings.get(f"state.{state}", state).upper()
            for state in ("listening", "armed", "recording", "transcribing", "executing")
        }
        labels["no_match"] = strings.get("overview.no_match", "no match").upper()
        labels["now_playing"] = strings.get("hud.now_playing", "now playing").upper()
        labels["placement"] = strings.get("hud.placement", "Drag me into place")
        labels["placement_done"] = strings.get("hud.placement_done", "Done")
        self._push({"type": "labels", "labels": labels})

    def _push(self, event: dict[str, Any]) -> None:
        if not self._ready.is_set() or self.window is None:
            return
        try:
            payload = json.dumps(event, ensure_ascii=False)
            self.window.evaluate_js(f"window.hudEvent && window.hudEvent({payload})")
        except Exception:
            # The window can be torn down between the check and the call.
            pass
