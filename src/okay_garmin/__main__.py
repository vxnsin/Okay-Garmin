"""Entry point for `python -m okay_garmin` and for the PyInstaller build."""

import sys

from .app import main

if __name__ == "__main__":
    sys.exit(main())
