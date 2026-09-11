"""Stage 2: transcribe the command with faster-whisper.

Only runs after the wake word (or push-to-talk), so the cost is paid per
command rather than continuously. int8 on CPU keeps memory around 150 MB and
turns a two-second clip around in roughly a third of a second.
"""

from __future__ import annotations

import numpy as np

from ..logging_setup import get_logger
from ..models import whisper_dir

log = get_logger("whisper")


class CommandTranscriber:
    def __init__(
        self,
        size: str = "base",
        language: str = "de",
        compute_type: str = "int8",
    ) -> None:
        from faster_whisper import WhisperModel

        self.language = language
        self.size = size
        log.info("Loading Whisper %s (%s)...", size, compute_type)
        self._model = WhisperModel(
            size,
            device="cpu",
            compute_type=compute_type,
            download_root=str(whisper_dir()),
            cpu_threads=min(4, __import__("os").cpu_count() or 2),
        )
        log.info("Whisper ready")

    def transcribe(self, pcm: bytes) -> str:
        """Transcribe raw 16 kHz mono int16 PCM."""
        if not pcm:
            return ""

        audio = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768.0
        if audio.size < 1600:  # shorter than 100 ms -- nothing was said
            return ""

        try:
            segments, _info = self._model.transcribe(
                audio,
                language=self.language,
                beam_size=1,
                # Each command is independent; carrying context over makes
                # Whisper invent continuations of the previous one.
                condition_on_previous_text=False,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 300},
            )
            text = " ".join(segment.text for segment in segments).strip()
        except Exception as exc:
            log.error("Transcription failed: %s", exc)
            return ""

        log.debug("Transcribed: %r", text)
        return text
