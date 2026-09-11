"""Download and locate the offline speech models.

Models are deliberately *not* bundled in the installer: together they are
~185 MB, which would quadruple the download for users who never change the
default language. They are fetched once on first run instead.
"""

from __future__ import annotations

import os
import shutil
import zipfile
from collections.abc import Callable
from pathlib import Path

import requests

from .logging_setup import get_logger
from .paths import models_dir

# Windows without Developer Mode cannot make symlinks, and huggingface_hub
# warns about it on every download. The degraded mode it falls back to is fine
# for us -- we only ever store one snapshot per model.
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")

log = get_logger("models")

ProgressFn = Callable[[str, float, str], None]

VOSK_MODELS = {
    "de": ("vosk-model-small-de-0.15", 45),
    "en": ("vosk-model-small-en-us-0.15", 40),
    "fr": ("vosk-model-small-fr-0.22", 41),
    "es": ("vosk-model-small-es-0.42", 39),
    "it": ("vosk-model-small-it-0.22", 48),
}

VOSK_BASE_URL = "https://alphacephei.com/vosk/models"

WHISPER_SIZES_MB = {"tiny": 75, "base": 145, "small": 480}


def _noop(stage: str, fraction: float, message: str) -> None:
    return None


def vosk_dir() -> Path:
    return models_dir() / "vosk"


def whisper_dir() -> Path:
    return models_dir() / "whisper"


def vosk_model_path(language: str) -> Path | None:
    """Path to an already-downloaded Vosk model, or None."""
    entry = VOSK_MODELS.get(language)
    if entry is None:
        return None
    path = vosk_dir() / entry[0]
    return path if (path / "am").is_dir() or (path / "am_tdnn").is_dir() else None


def whisper_is_downloaded(size: str) -> bool:
    root = whisper_dir()
    if not root.is_dir():
        return False
    # faster-whisper stores HF snapshots as models--Systran--faster-whisper-<size>.
    needle = f"faster-whisper-{size}"
    return any(needle in p.name for p in root.iterdir())


def download_status(language: str, whisper_size: str) -> dict:
    return {
        "vosk": {
            "language": language,
            "available": vosk_model_path(language) is not None,
            "supported": language in VOSK_MODELS,
            "size_mb": VOSK_MODELS.get(language, ("", 45))[1],
        },
        "whisper": {
            "size": whisper_size,
            "available": whisper_is_downloaded(whisper_size),
            "size_mb": WHISPER_SIZES_MB.get(whisper_size, 145),
        },
    }


def ensure_vosk(language: str, progress: ProgressFn = _noop) -> Path:
    """Download and unpack the Vosk model for `language` if it isn't there yet."""
    entry = VOSK_MODELS.get(language)
    if entry is None:
        raise ValueError(f"No Vosk model available for language {language!r}")

    name = entry[0]
    target = vosk_dir() / name
    if vosk_model_path(language) is not None:
        return target

    vosk_dir().mkdir(parents=True, exist_ok=True)
    url = f"{VOSK_BASE_URL}/{name}.zip"
    archive = vosk_dir() / f"{name}.zip.part"

    log.info("Downloading Vosk model %s", name)
    progress("vosk", 0.0, f"Downloading {name}")

    with requests.get(url, stream=True, timeout=60) as response:
        response.raise_for_status()
        total = int(response.headers.get("Content-Length", 0))
        done = 0
        with archive.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=1 << 16):
                handle.write(chunk)
                done += len(chunk)
                if total:
                    progress("vosk", done / total * 0.9, f"Downloading {name}")

    progress("vosk", 0.92, "Extracting")
    staging = vosk_dir() / f".{name}.staging"
    if staging.exists():
        shutil.rmtree(staging, ignore_errors=True)
    with zipfile.ZipFile(archive) as archive_file:
        archive_file.extractall(staging)

    # The zip contains a single top-level directory; move it into place atomically.
    extracted = staging / name
    source = extracted if extracted.is_dir() else next(staging.iterdir())
    if target.exists():
        shutil.rmtree(target, ignore_errors=True)
    shutil.move(str(source), str(target))
    shutil.rmtree(staging, ignore_errors=True)
    archive.unlink(missing_ok=True)

    progress("vosk", 1.0, "Ready")
    log.info("Vosk model ready at %s", target)
    return target


def ensure_whisper(size: str, progress: ProgressFn = _noop) -> str:
    """Make sure the faster-whisper snapshot is on disk. Returns the model id."""
    from faster_whisper.utils import download_model

    whisper_dir().mkdir(parents=True, exist_ok=True)
    if whisper_is_downloaded(size):
        return size

    log.info("Downloading Whisper model %s", size)
    progress("whisper", 0.0, f"Downloading Whisper {size}")
    # download_model reports no progress of its own; the UI shows an
    # indeterminate state for this stage.
    download_model(size, cache_dir=str(whisper_dir()))
    progress("whisper", 1.0, "Ready")
    log.info("Whisper model %s ready", size)
    return size


def ensure_all(language: str, whisper_size: str, progress: ProgressFn = _noop) -> None:
    ensure_vosk(language, progress)
    ensure_whisper(whisper_size, progress)
