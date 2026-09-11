"""PyInstaller entry point for the application.

PyInstaller runs its entry script as a top-level module with no parent package,
so `src/okay_garmin/__main__.py` (which uses relative imports) cannot serve as
one. This file imports absolutely instead; `python -m okay_garmin` still works
through __main__.py.
"""

import sys

from okay_garmin.app import main

if __name__ == "__main__":
    sys.exit(main())
