"""System tray icon and menu."""

from __future__ import annotations

import pystray
from PIL import Image
from pystray import Menu, MenuItem

from .logging_setup import get_logger
from .paths import icon_path
from .version import APP_NAME, __version__

log = get_logger("tray")

LABELS = {
    "de": {
        "settings": "Einstellungen",
        "pause": "Lauschen pausieren",
        "resume": "Lauschen fortsetzen",
        "updates": "Nach Updates suchen",
        "quit": "Beenden",
    },
    "en": {
        "settings": "Settings",
        "pause": "Pause listening",
        "resume": "Resume listening",
        "updates": "Check for updates",
        "quit": "Quit",
    },
}


def _labels(language: str) -> dict[str, str]:
    return LABELS.get(language, LABELS["en"])


class Tray:
    def __init__(self, app) -> None:
        self._app = app
        self.icon: pystray.Icon | None = None

    def _text(self, key: str) -> str:
        from . import config as config_module

        return _labels(config_module.get("ui_language", "de"))[key]

    def build(self) -> pystray.Icon:
        image = Image.open(icon_path())

        menu = Menu(
            MenuItem(f"{APP_NAME} v{__version__}", None, enabled=False),
            Menu.SEPARATOR,
            MenuItem(lambda _: self._text("settings"), self._open_settings, default=True),
            MenuItem(
                lambda _: self._text("resume") if self._app.engine.paused else self._text("pause"),
                self._toggle_pause,
            ),
            MenuItem(lambda _: self._text("updates"), self._check_updates),
            Menu.SEPARATOR,
            MenuItem(lambda _: self._text("quit"), self._quit),
        )

        self.icon = pystray.Icon(APP_NAME, image, APP_NAME, menu)
        return self.icon

    def refresh(self) -> None:
        """Redraw the menu, e.g. after pause state or language changed."""
        if self.icon is not None:
            try:
                self.icon.update_menu()
            except Exception as exc:
                log.debug("Could not refresh the tray menu: %s", exc)

    def set_tooltip(self, text: str) -> None:
        if self.icon is not None:
            try:
                self.icon.title = f"{APP_NAME} - {text}"
            except Exception:
                pass

    def stop(self) -> None:
        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:
                pass

    # ------------------------------------------------------------------ handlers

    def _open_settings(self, icon=None, item=None) -> None:
        self._app.show_settings()

    def _toggle_pause(self, icon=None, item=None) -> None:
        self._app.engine.set_paused(not self._app.engine.paused)
        self.refresh()

    def _check_updates(self, icon=None, item=None) -> None:
        self._app.check_for_updates(notify_when_current=True)

    def _quit(self, icon=None, item=None) -> None:
        self._app.quit()
