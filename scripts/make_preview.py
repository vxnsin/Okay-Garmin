"""Render web/index.html with a stubbed pywebview bridge, for eyeballing the UI.

Writes web/_preview.html, which is git-ignored and safe to delete. Useful when
you want to look at the interface without starting the whole app.

    uv run python scripts/make_preview.py && start web/_preview.html
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

from okay_garmin.config import DEFAULT_CONFIG  # noqa: E402

WEB = ROOT / "web"


def build_config() -> dict:
    config = json.loads(json.dumps(DEFAULT_CONFIG))
    config["spotify"]["client_id"] = "3f9a1c2b4d5e6f7a8b9c0d1e2f3a4b5c"
    config["voice_commands"] += [
        {
            # Deliberately missing its {} -- shows the editor warning.
            "command": "spiel was schoenes",
            "aliases": [],
            "type": "spotify",
            "value": "play",
            "delay": 0,
            "enabled": True,
        },
        {
            "command": "musik pause",
            "aliases": ["pause musik", "stopp die musik"],
            "type": "hotkey",
            "value": "mediaplay",
            "delay": 0,
            "enabled": True,
        },
        {
            "command": "ordner oeffnen",
            "aliases": [],
            "type": "folder",
            "value": r"C:\Users\vensin\Desktop\Clips",
            "delay": 1.5,
            "enabled": False,
        },
    ]
    return config


def build_stub() -> str:
    translations = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in (WEB / "i18n").glob("*.json")
    }

    responses = {
        "get_config": build_config(),
        "get_translations": translations,
        "get_devices": [
            {"index": 1, "name": "Surface-Stereo-Mikrofone", "default": True},
            {"index": 3, "name": "USB Headset (Logitech)", "default": False},
        ],
        "get_app_info": {
            "version": "v2.0.0",
            "wake_word": "okay garmin",
            "repo": "https://github.com/vxnsin/Okay-Garmin",
            "frozen": True,
            "config_path": r"C:\Users\vensin\AppData\Roaming\Okay-Garmin\config.json",
            "log_path": r"C:\Users\vensin\AppData\Roaming\Okay-Garmin\logs",
        },
        "get_status": {
            "state": "listening",
            "paused": False,
            "error": None,
            "history": [
                {"text": "musik pause bitte", "matched": "musik pause", "score": 0.88},
                {"text": "wie spaet ist es", "matched": None, "score": 0.41},
                {"text": "video speichern", "matched": "video speichern", "score": 0.97},
            ],
        },
        "get_models_status": {
            "vosk": {"language": "de", "available": True, "supported": True, "size_mb": 45},
            "whisper": {"size": "base", "available": True, "size_mb": 145},
        },
        "get_autostart": True,
        "get_spotify_status": {
            "connected": False,
            "client_id": "",
            "configured": False,
            "redirect_uri": "http://127.0.0.1:8888/callback",
        },
        "get_version": {
            "current": "v2.0.0",
            "latest": "v2.1.0",
            "update_available": True,
            "checked": True,
            "repo": "https://github.com/vxnsin/Okay-Garmin",
        },
    }

    return (
        "<script>\n"
        f"const STUB = {json.dumps(responses, ensure_ascii=False)};\n"
        "window.pywebview = { api: new Proxy({}, { get: (_t, name) => async (arg) => {\n"
        "  if (name in STUB) return STUB[name];\n"
        "  if (name === 'set_autostart') return { status: 'ok', enabled: arg, supported: true };\n"
        "  return { status: 'ok' };\n"
        "} }) };\n"
        "window.addEventListener('load', () => setTimeout(() => {\n"
        "  window.dispatchEvent(new Event('pywebviewready'));\n"
        "  setTimeout(() => setInterval(() => window.ogEvent({ type: 'level', "
        "level: 0.2 + Math.random() * 0.55 }), 130), 500);\n"
        "}, 50));\n"
        "</script>\n"
    )


def inline_assets(html: str) -> str:
    """Fold the stylesheet and scripts into the page.

    Preview hosts may serve the file from a data: URL, where relative paths
    resolve to nothing -- a self-contained page renders the same everywhere.
    """
    css = (WEB / "css" / "app.css").read_text(encoding="utf-8")
    html = html.replace(
        '<link rel="stylesheet" href="css/app.css" />',
        f"<style>\n{css}\n</style>",
    )
    for name in ("i18n", "hotkey", "app"):
        script = (WEB / "js" / f"{name}.js").read_text(encoding="utf-8")
        html = html.replace(
            f'<script src="js/{name}.js"></script>',
            f"<script>\n{script}\n</script>",
        )
    return html


def main() -> int:
    source = (WEB / "index.html").read_text(encoding="utf-8")
    marker = '<script src="js/i18n.js"></script>'
    if marker not in source:
        print("index.html no longer contains the i18n script tag", file=sys.stderr)
        return 1

    html = inline_assets(source.replace(marker, build_stub() + marker))
    target = WEB / "_preview.html"
    target.write_text(html, encoding="utf-8")
    print(f"Wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
