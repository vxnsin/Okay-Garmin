"""Stage 1: always-on wake-word detection with Vosk.

The trick that makes this cheap enough to run permanently is the restricted
grammar: instead of decoding against the model's full vocabulary, Vosk is
given just the wake word plus "[unk]". That cuts idle CPU to a few percent of
one core and, as a bonus, sharply reduces false triggers -- there is almost
nothing else it *can* output.
"""

from __future__ import annotations

import json

from ..logging_setup import get_logger
from .matching import normalize, phrase_score

log = get_logger("wake")


class WakeWordDetector:
    def __init__(self, model_path: str, wake_word: str, threshold: float = 0.75) -> None:
        from vosk import KaldiRecognizer, Model, SetLogLevel

        SetLogLevel(-1)  # Vosk is extremely chatty on stdout otherwise.

        self.wake_word = normalize(wake_word)
        self.threshold = threshold
        self._model = Model(model_path)
        self._recognizer = self._build_recognizer()
        log.info("Wake word detector ready for %r", wake_word)

    def _build_recognizer(self):
        from vosk import KaldiRecognizer

        from .audio import SAMPLE_RATE

        grammar = json.dumps([self.wake_word, "[unk]"], ensure_ascii=False)
        recognizer = KaldiRecognizer(self._model, SAMPLE_RATE, grammar)
        recognizer.SetWords(False)
        return recognizer

    def set_wake_word(self, wake_word: str) -> None:
        new = normalize(wake_word)
        if new == self.wake_word:
            return
        self.wake_word = new
        self._recognizer = self._build_recognizer()
        log.info("Wake word changed to %r", wake_word)

    def reset(self) -> None:
        """Clear decoder state, e.g. after a command ran."""
        self._recognizer = self._build_recognizer()

    def accept(self, block: bytes) -> tuple[bool, str]:
        """Feed one audio block. Returns (wake_detected, recognised_text)."""
        try:
            if self._recognizer.AcceptWaveform(block):
                text = json.loads(self._recognizer.Result()).get("text", "")
            else:
                text = json.loads(self._recognizer.PartialResult()).get("partial", "")
        except Exception as exc:
            log.warning("Vosk decode failed: %s", exc)
            return False, ""

        if not text:
            return False, ""

        score = phrase_score(text, self.wake_word)
        if score >= self.threshold:
            log.debug("Wake word hit: %r (%.2f)", text, score)
            self.reset()
            return True, text
        return False, text
