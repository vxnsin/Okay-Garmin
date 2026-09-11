"""The updater, built as its own small update.exe.

Flow: ask the running app to quit, download the setup for the newest release,
verify its SHA-256 against latest.json, then run it silently. The installer's
own [Run] section starts the app again.

v1 swapped main.exe in place, which failed as soon as Windows held a lock on
the file -- and it verified nothing it downloaded.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from ..logging_setup import setup_logging
from ..single_instance import QUIT_EVENT_NAME, signal_existing_instance
from ..version import APP_NAME
from .core import (
    check_for_update,
    current_version,
    download,
    fetch_latest_release,
    fetch_manifest,
    parse_version,
    sha256_file,
)

log = setup_logging()


def _stop_running_app(timeout: float = 20.0) -> None:
    """Ask the app to exit, then wait for it to release its mutex."""
    if not signal_existing_instance(QUIT_EVENT_NAME):
        log.info("No running instance to stop")
        return

    log.info("Asked the running instance to quit")
    import win32api
    import win32event
    import winerror

    from ..single_instance import MUTEX_NAME

    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        handle = win32event.CreateMutex(None, False, MUTEX_NAME)
        already_running = win32api.GetLastError() == winerror.ERROR_ALREADY_EXISTS
        win32api.CloseHandle(handle)
        if not already_running:
            log.info("Application closed")
            return
        time.sleep(0.5)

    log.warning("Application did not close in time -- the installer will handle it")


def main() -> int:
    print(f"=== {APP_NAME} Updater ===")

    info = check_for_update()
    if not info["checked"]:
        print("Could not reach GitHub. Check your internet connection.")
        return 1

    print(f"Installed: {info['current']}   Latest: {info['latest']}")
    if not info["update_available"]:
        print("Already up to date.")
        return 0

    release = fetch_latest_release()
    if release is None:
        return 1

    tag = release.get("tag_name", "")
    latest = parse_version(tag)
    if latest is None or latest <= current_version():
        print("Nothing newer to install.")
        return 0

    url = info["url"]
    if not url:
        print("This release has no installer attached.")
        return 1

    manifest = fetch_manifest(release)
    expected = (manifest or {}).get("sha256")
    if not expected:
        # Refuse rather than run an unverified executable.
        print("Release manifest is missing a checksum -- aborting for safety.")
        print(f"Download and install it manually: {url}")
        return 1

    target = Path(tempfile.gettempdir()) / f"{APP_NAME}-Setup-{latest}.exe"
    print("Downloading update...")

    def progress(fraction: float) -> None:
        sys.stdout.write(f"\r  {fraction * 100:5.1f}%")
        sys.stdout.flush()

    try:
        download(url, target, progress)
    except Exception as exc:
        print(f"\nDownload failed: {exc}")
        return 1
    print()

    actual = sha256_file(target)
    if actual.lower() != expected.lower():
        print("Checksum mismatch -- the download was corrupted or tampered with.")
        log.error("SHA-256 mismatch: expected %s, got %s", expected, actual)
        target.unlink(missing_ok=True)
        return 1
    print("Checksum verified.")

    _stop_running_app()

    print("Installing...")
    try:
        subprocess.Popen(
            [str(target), "/SILENT", "/NORESTART", "/SUPPRESSMSGBOXES"],
            close_fds=True,
        )
    except OSError as exc:
        print(f"Could not start the installer: {exc}")
        return 1

    print("The installer is running. It will restart the app when it is done.")
    # Exit immediately: the installer needs to replace this executable too.
    os._exit(0)


if __name__ == "__main__":
    sys.exit(main())
