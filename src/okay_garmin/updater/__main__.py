"""Allows `python -m okay_garmin.updater`."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
