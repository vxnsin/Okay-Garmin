"""Where everything lives on disk.

v1 kept config.json next to the .exe. That breaks the moment an installer
replaces the program folder on update, so v2 moves user data to %APPDATA%
and migrates the old file on first start.
"""

import os
import sys
from pathlib import Path

from .version import APP_NAME


def is_frozen() -> bool:
    return getattr(sys, "frozen", False)


def app_dir() -> Path:
    """Directory the executable (or source tree) lives in."""
    if is_frozen():
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent.parent


def data_dir() -> Path:
    r"""%APPDATA%\Okay-Garmin -- config, logs and speech models."""
    base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
    path = Path(base) / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path() -> Path:
    return data_dir() / "config.json"


def log_dir() -> Path:
    path = data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def models_dir() -> Path:
    path = data_dir() / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path


def legacy_config_path() -> Path:
    """Where v1.x stored config.json -- next to the executable."""
    return app_dir() / "config.json"


def resource_path(*parts: str) -> Path:
    """Resolve a bundled resource, both frozen (PyInstaller _MEIPASS) and from source."""
    base = Path(getattr(sys, "_MEIPASS", "")) if hasattr(sys, "_MEIPASS") else None
    if base is None:
        base = Path(__file__).resolve().parent.parent.parent
    return base.joinpath(*parts)


def web_dir() -> Path:
    return resource_path("web")


def sounds_dir() -> Path:
    """Sounds ship next to the executable so users can swap them out."""
    bundled = resource_path("sounds")
    if bundled.is_dir():
        return bundled
    return app_dir() / "sounds"


def icon_path() -> Path:
    for candidate in (resource_path("assets", "icon.ico"), resource_path("icon.ico")):
        if candidate.is_file():
            return candidate
    return resource_path("assets", "icon.ico")


def executable_path() -> str:
    """The command Windows should run to start us -- used for autostart."""
    return os.path.realpath(sys.executable)
