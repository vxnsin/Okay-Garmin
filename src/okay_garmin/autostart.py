r"""Windows autostart via HKCU\...\Run.

This is the README's "Fix Autostart recognition" item. v1 had two bugs:

  1. It wrote the bare path, so any install directory containing a space
     (the default "C:\Program Files\..." among them) never started.
  2. get_autostart() returned `os.path.exists(value) or value == sys.executable`,
     which reports "enabled" for a stale entry pointing at a *different*
     program that happens to exist.

v2 stores a quoted path and compares normalised real paths.
"""

import os
import winreg

from .logging_setup import get_logger
from .paths import executable_path, is_frozen
from .version import APP_NAME

log = get_logger("autostart")

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = APP_NAME


def _unquote(value: str) -> str:
    value = value.strip()
    if value.startswith('"'):
        # Registry Run values are "path" followed by optional arguments.
        end = value.find('"', 1)
        if end != -1:
            return value[1:end]
    return value.split(" ")[0] if " " not in value else value


def _same_target(stored: str) -> bool:
    try:
        a = os.path.normcase(os.path.realpath(_unquote(stored)))
        b = os.path.normcase(os.path.realpath(executable_path()))
        return a == b
    except OSError:
        return False


def _read_value() -> str | None:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, VALUE_NAME)
            return value
    except FileNotFoundError:
        return None
    except OSError as exc:
        log.warning("Could not read autostart entry: %s", exc)
        return None


def is_enabled() -> bool:
    """True only when the entry exists *and* points at this executable."""
    stored = _read_value()
    if stored is None:
        return False
    return _same_target(stored)


def set_enabled(enable: bool) -> bool:
    if not is_frozen():
        # From source, sys.executable is python.exe -- registering that is useless.
        log.info("Autostart change ignored: not running as a packaged build")
        return False

    try:
        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE
        ) as key:
            if enable:
                winreg.SetValueEx(
                    key, VALUE_NAME, 0, winreg.REG_SZ, f'"{executable_path()}"'
                )
                log.info("Autostart enabled")
            else:
                try:
                    winreg.DeleteValue(key, VALUE_NAME)
                    log.info("Autostart disabled")
                except FileNotFoundError:
                    pass
        return enable
    except OSError as exc:
        log.error("Could not change autostart: %s", exc)
        return is_enabled()


def repair() -> None:
    """After an update or a move, point a stale entry at the new location.

    Only touches an entry that already exists -- it never opts the user in.
    """
    stored = _read_value()
    if stored is None or _same_target(stored):
        return
    log.info("Autostart entry points elsewhere (%s) -- repairing", stored)
    set_enabled(True)
