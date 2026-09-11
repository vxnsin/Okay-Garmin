"""Configuration: defaults, load/save, and migration from older layouts."""

import json
import shutil
import threading
from typing import Any

from .logging_setup import get_logger
from .paths import config_path, legacy_config_path

log = get_logger("config")

SCHEMA_VERSION = 3

DEFAULT_CONFIG: dict[str, Any] = {
    "schema_version": SCHEMA_VERSION,
    "ui_language": "de",
    "theme": "dark",
    "sound_enabled": True,
    "notifications_enabled": True,
    "command_timeout": 6.0,
    "match_threshold": 0.72,
    "cooldown": 2.0,
    "input_device": None,
    "stt": {
        "language": "de",
        "whisper_model": "base",
        "compute_type": "int8",
    },
    "push_to_talk": {
        "enabled": True,
        "hotkey": "ctrl+alt+g",
    },
    "overlay": {
        "enabled": True,
        # A preset corner, unless the user placed it by hand.
        "position": "bottom-center",
        "custom": False,
        "x": None,
        "y": None,
        "scale": 1.0,
        "hide_after": 2.5,
        "show_cover": True,
    },
    "spotify": {
        # The user registers their own app at developer.spotify.com; PKCE means
        # there is no secret to store.
        "client_id": "",
    },
    "voice_commands": [
        {
            "command": "video speichern",
            "aliases": [],
            "type": "hotkey",
            "value": "f8",
            "delay": 0,
            "enabled": True,
        },
        # {} marks the free-text part: whatever follows is handed to Spotify.
        {
            "command": "spiel {}",
            "aliases": ["spiele {}", "mach {} an"],
            "type": "spotify",
            "value": "play",
            "delay": 0,
            "enabled": True,
        },
        # Media keys need no account and work with any player.
        {
            "command": "musik pause",
            # Not "weiter": it appears inside ordinary sentences, and it means
            # resume rather than pause.
            "aliases": ["stopp die musik", "pausiere die musik"],
            "type": "media",
            "value": "play_pause",
            "delay": 0,
            "enabled": True,
        },
        {
            "command": "naechster song",
            "aliases": ["nachster song", "skip"],
            "type": "media",
            "value": "next",
            "delay": 0,
            "enabled": True,
        },
        {
            "command": "letzter song",
            "aliases": ["vorheriger song"],
            "type": "media",
            "value": "previous",
            "delay": 0,
            "enabled": True,
        },
    ],
}

_lock = threading.Lock()
_config: dict[str, Any] = {}


def _deep_merge(defaults: dict, loaded: dict) -> dict:
    """Fill in keys a user's config predates, without clobbering their values."""
    result = dict(defaults)
    for key, value in loaded.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def _migrate(raw: dict) -> dict:
    """Lift a v1 config onto the v2 schema."""
    version = raw.get("schema_version", 1)
    if version >= SCHEMA_VERSION:
        return raw

    log.info("Migrating config from schema v%s to v%s", version, SCHEMA_VERSION)
    for cmd in raw.get("voice_commands", []):
        cmd.setdefault("aliases", [])
        cmd.setdefault("delay", 0)
        cmd.setdefault("enabled", True)
    raw["schema_version"] = SCHEMA_VERSION
    return raw


def load_config() -> dict[str, Any]:
    global _config
    path = config_path()

    # v1 stored config.json beside the executable -- bring it along, keep the original.
    if not path.exists():
        legacy = legacy_config_path()
        if legacy.exists() and legacy != path:
            try:
                shutil.copy2(legacy, path)
                log.info("Migrated config from %s", legacy)
            except OSError as exc:
                log.warning("Could not migrate legacy config: %s", exc)

    if path.exists():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("config root is not an object")
            with _lock:
                _config = _deep_merge(DEFAULT_CONFIG, _migrate(raw))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            log.warning("Config unreadable (%s) -- starting from defaults", exc)
            backup = path.with_suffix(".json.broken")
            try:
                shutil.copy2(path, backup)
                log.info("Broken config kept at %s", backup)
            except OSError:
                pass
            with _lock:
                _config = json.loads(json.dumps(DEFAULT_CONFIG))
    else:
        with _lock:
            _config = json.loads(json.dumps(DEFAULT_CONFIG))
        log.info("Created new config at %s", path)

    save_config()
    return get_config()


def get_config() -> dict[str, Any]:
    with _lock:
        return json.loads(json.dumps(_config))


def set_config(new_config: dict[str, Any]) -> dict[str, Any]:
    global _config
    with _lock:
        _config = _deep_merge(DEFAULT_CONFIG, new_config)
    save_config()
    return get_config()


def get(key: str, default: Any = None) -> Any:
    """Read a dotted path, e.g. get("push_to_talk.hotkey")."""
    node: Any = _config
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return default
        node = node[part]
    return node


def save_config() -> None:
    path = config_path()
    tmp = path.with_suffix(".json.tmp")
    with _lock:
        payload = json.dumps(_config, indent=4, ensure_ascii=False)
    try:
        # Write-then-replace: a crash mid-save must not leave a truncated config.
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(path)
    except OSError as exc:
        log.error("Could not save config: %s", exc)
