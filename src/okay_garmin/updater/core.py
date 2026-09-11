"""Shared update logic: what is the latest release, and is it newer than us?

v1 detected the version by following the /releases/latest redirect and
regexing the resulting URL, then compared tags with `!=`. That reported an
update whenever the strings differed at all (including downgrades) and got the
ordering wrong for two-digit minors -- "v1.10" compared as older than "v1.9".
v2 uses the JSON API and real version parsing.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import requests
from packaging.version import InvalidVersion, Version

from ..logging_setup import get_logger
from ..version import GITHUB_API, __version__

log = get_logger("updater")

SETUP_ASSET_PREFIX = "Okay-Garmin-Setup"
MANIFEST_ASSET = "latest.json"


def parse_version(tag: str) -> Version | None:
    try:
        return Version(tag.lstrip("vV"))
    except InvalidVersion:
        return None


def current_version() -> Version:
    return Version(__version__)


def fetch_latest_release(timeout: float = 10.0) -> dict[str, Any] | None:
    try:
        response = requests.get(
            f"{GITHUB_API}/releases/latest",
            timeout=timeout,
            headers={"Accept": "application/vnd.github+json"},
        )
        response.raise_for_status()
        return response.json()
    except requests.RequestException as exc:
        log.warning("Could not reach GitHub: %s", exc)
        return None
    except ValueError as exc:
        log.warning("GitHub returned something that is not JSON: %s", exc)
        return None


def _find_asset(release: dict, predicate) -> dict | None:
    for asset in release.get("assets", []):
        if predicate(asset.get("name", "")):
            return asset
    return None


def check_for_update(timeout: float = 10.0) -> dict[str, Any]:
    """Returns current/latest versions and whether an update is available."""
    result = {
        "current": f"v{__version__}",
        "latest": f"v{__version__}",
        "update_available": False,
        "url": None,
        "notes": "",
        "checked": False,
    }

    release = fetch_latest_release(timeout)
    if release is None:
        return result

    tag = release.get("tag_name", "")
    latest = parse_version(tag)
    result["checked"] = True
    if latest is None:
        log.warning("Could not parse release tag %r", tag)
        return result

    result["latest"] = f"v{latest}"
    result["notes"] = (release.get("body") or "")[:2000]
    result["update_available"] = latest > current_version()

    asset = _find_asset(release, lambda name: name.startswith(SETUP_ASSET_PREFIX) and name.endswith(".exe"))
    if asset:
        result["url"] = asset.get("browser_download_url")
    elif result["update_available"]:
        # Nothing to install -- don't offer an update we cannot perform.
        log.warning("Release %s has no setup asset", tag)
        result["update_available"] = False

    return result


def fetch_manifest(release: dict) -> dict[str, Any] | None:
    """The latest.json we attach to each release, carrying the setup SHA-256."""
    asset = _find_asset(release, lambda name: name == MANIFEST_ASSET)
    if asset is None:
        return None
    try:
        response = requests.get(asset["browser_download_url"], timeout=15)
        response.raise_for_status()
        return response.json()
    except (requests.RequestException, ValueError) as exc:
        log.warning("Could not read %s: %s", MANIFEST_ASSET, exc)
        return None


def sha256_file(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, target: Path, progress=None) -> Path:
    log.info("Downloading %s", url)
    with requests.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        total = int(response.headers.get("Content-Length", 0))
        done = 0
        with target.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1 << 16):
                handle.write(chunk)
                done += len(chunk)
                if progress and total:
                    progress(done / total)
    return target
