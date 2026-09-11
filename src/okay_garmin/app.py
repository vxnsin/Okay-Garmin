"""Application entry point: wires engine, tray, settings window and overlay together."""

from __future__ import annotations

import argparse
import json
import os
import threading
from typing import Any

from . import autostart
from . import config as config_module
from .api import Api
from .engine import VoiceEngine
from .logging_setup import setup_logging
from .overlay import Overlay
from .paths import icon_path, web_dir
from .ptt import PushToTalk
from .single_instance import (
    QUIT_EVENT_NAME,
    SHOW_EVENT_NAME,
    acquire,
    signal_existing_instance,
    watch_event,
)
from .tray import Tray
from .updater.core import check_for_update
from .version import APP_NAME, __version__

log = setup_logging()

STATUS_TOOLTIPS = {
    "listening": "listening",
    "armed": "waiting for a command",
    "recording": "recording",
    "transcribing": "transcribing",
    "executing": "running a command",
    "paused": "paused",
    "downloading": "downloading models",
    "error": "error",
}


class Application:
    def __init__(self) -> None:
        self.engine = VoiceEngine()
        # When the user finishes placing the HUD, bring the settings back.
        self.overlay = Overlay(on_placement_end=self._placement_ended)
        self.tray = Tray(self)
        self.ptt = PushToTalk(self.engine.ptt_press, self.engine.ptt_release)
        self.window = None
        self._stop = threading.Event()
        self._ui_ready = threading.Event()
        self.show_on_start = False

    # ------------------------------------------------------------------ UI bridge

    def broadcast(self, event: dict[str, Any]) -> None:
        """Forward an event to the settings window and the HUD."""
        self.overlay.handle_event(event)

        if event.get("type") == "state":
            self.tray.set_tooltip(STATUS_TOOLTIPS.get(event.get("state", ""), ""))
            self.tray.refresh()

        if self.window is None or not self._ui_ready.is_set():
            return
        try:
            payload = json.dumps(event, ensure_ascii=False)
            self.window.evaluate_js(f"window.ogEvent && window.ogEvent({payload})")
        except Exception:
            # Window closed between the check and the call -- nothing to do.
            pass

    def _placement_ended(self) -> None:
        self.broadcast({"type": "placement_ended"})
        self.show_settings()

    def _on_ui_loaded(self) -> None:
        self._ui_ready.set()

    def show_settings(self) -> None:
        if self.window is None:
            return
        try:
            self.window.show()
            self.window.restore()
            self.window.on_top = True
            self.window.on_top = False
        except Exception as exc:
            log.debug("Could not show the settings window: %s", exc)

    def hide_settings(self) -> None:
        if self.window is not None:
            try:
                self.window.hide()
            except Exception:
                pass

    # ------------------------------------------------------------------ updates

    def check_for_updates(self, notify_when_current: bool = False) -> None:
        def worker() -> None:
            info = check_for_update()
            self.broadcast({"type": "update_info", **info})
            if not info["checked"]:
                return

            if info["update_available"]:
                self._notify(
                    "Update available",
                    f"{info['latest']} is ready to install.",
                )
            elif notify_when_current:
                self._notify("Up to date", f"You are running {info['current']}.")

        threading.Thread(target=worker, name="update-check", daemon=True).start()

    def _notify(self, title: str, message: str) -> None:
        if not config_module.get("notifications_enabled", True):
            return
        try:
            from winotify import Notification

            Notification(
                app_id=APP_NAME,
                title=title,
                msg=message,
                icon=str(icon_path()),
                duration="short",
            ).show()
        except Exception as exc:
            log.debug("Could not show a notification: %s", exc)

    # ------------------------------------------------------------------ lifecycle

    def quit(self) -> None:
        log.info("Shutting down")
        self._stop.set()
        self.engine.stop()
        self.ptt.stop()
        self.tray.stop()
        try:
            if self.window is not None:
                self.window.destroy()
        except Exception:
            pass
        # pywebview's loop does not always unwind cleanly from a tray thread.
        os._exit(0)

    def run(self) -> None:
        import webview

        cfg = config_module.load_config()
        log.info("%s v%s starting", APP_NAME, __version__)

        autostart.repair()

        api = Api(self)
        self.window = webview.create_window(
            f"{APP_NAME} - Settings",
            str(web_dir() / "index.html"),
            js_api=api,
            width=1020,
            height=680,
            min_size=(840, 560),
            # Start hidden unless asked for. Never call show() from the UI
            # thread's own loaded handler -- it waits on that same thread.
            hidden=not self.show_on_start,
        )

        def on_closing() -> bool:
            # Closing the window only hides it -- the app lives in the tray.
            self.window.hide()
            return False

        self.window.events.closing += on_closing
        self.window.events.loaded += self._on_ui_loaded

        self.overlay.create()

        self.engine.subscribe(self.broadcast)
        self.ptt.configure(cfg["push_to_talk"]["enabled"], cfg["push_to_talk"]["hotkey"])
        self.ptt.start()

        tray_icon = self.tray.build()
        threading.Thread(target=tray_icon.run, name="tray", daemon=True).start()

        watch_event(QUIT_EVENT_NAME, self.quit, self._stop)
        watch_event(SHOW_EVENT_NAME, self.show_settings, self._stop)

        self.engine.start()
        self.check_for_updates()

        log.info("Ready")
        webview.start(debug=False)


def main() -> int:
    parser = argparse.ArgumentParser(prog="okay-garmin")
    parser.add_argument("--debug", action="store_true", help="verbose logging")
    parser.add_argument(
        "--settings", action="store_true", help="open the settings window on start"
    )
    args = parser.parse_args()

    setup_logging(debug=args.debug)

    if not acquire():
        # Hand over to the copy that is already running instead of fighting it
        # for the microphone.
        signal_existing_instance(SHOW_EVENT_NAME)
        print(f"{APP_NAME} is already running.")
        return 0

    app = Application()
    app.show_on_start = args.settings
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
