"""Rotating log file plus console output.

Local speech recognition fails in ways that are invisible without logs
(missing model, wrong microphone, no audio device at all), so v2 always
writes one.
"""

import logging
import sys
from logging.handlers import RotatingFileHandler

from .paths import log_dir

_configured = False


def setup_logging(debug: bool = False) -> logging.Logger:
    global _configured
    logger = logging.getLogger("okay_garmin")
    if _configured:
        return logger

    logger.setLevel(logging.DEBUG if debug else logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-7s  %(name)s: %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
    )

    file_handler = RotatingFileHandler(
        log_dir() / "okay-garmin.log",
        maxBytes=1_000_000,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)

    # A windowed PyInstaller build has no stdout at all -- guard before touching it.
    if sys.stdout is not None:
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass
        stream = logging.StreamHandler(sys.stdout)
        stream.setFormatter(fmt)
        logger.addHandler(stream)

    logger.propagate = False
    _configured = True
    return logger


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"okay_garmin.{name}")
