"""PyInstaller entry point for update.exe. See entrypoints/app.py for why."""

import sys

from okay_garmin.updater.cli import main

if __name__ == "__main__":
    sys.exit(main())
