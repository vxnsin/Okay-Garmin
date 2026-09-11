"""One shared 16 kHz microphone stream.

Both stages read from the same stream. Opening and closing the device per
utterance is slow and, on some Windows audio drivers, fails outright after a
few cycles -- so the stream stays open and the engine just switches what it
does with the blocks.
"""

from __future__ import annotations

import queue

import numpy as np
import sounddevice as sd

from ..logging_setup import get_logger

log = get_logger("audio")

SAMPLE_RATE = 16_000
BLOCK_FRAMES = 1_600  # 100 ms
BLOCK_SECONDS = BLOCK_FRAMES / SAMPLE_RATE


def list_input_devices() -> list[dict]:
    """Input devices suitable for the UI's microphone picker."""
    devices = []
    try:
        default_input = sd.default.device[0]
    except Exception:
        default_input = None

    try:
        for index, device in enumerate(sd.query_devices()):
            if device.get("max_input_channels", 0) < 1:
                continue
            devices.append(
                {
                    "index": index,
                    "name": device.get("name", f"Device {index}"),
                    "default": index == default_input,
                }
            )
    except Exception as exc:
        log.warning("Could not enumerate audio devices: %s", exc)
    return devices


def rms_level(block: bytes) -> float:
    """Normalised 0..1 loudness of a block of int16 PCM."""
    if not block:
        return 0.0
    samples = np.frombuffer(block, dtype=np.int16).astype(np.float32)
    if samples.size == 0:
        return 0.0
    rms = float(np.sqrt(np.mean(samples * samples)))
    return min(1.0, rms / 8000.0)


class AudioSource:
    """Blocking reader over a sounddevice callback stream."""

    def __init__(self, device: int | None = None, max_queue: int = 100) -> None:
        self.device = device
        self._queue: queue.Queue[bytes] = queue.Queue(maxsize=max_queue)
        self._stream: sd.RawInputStream | None = None
        self.overflows = 0

    def _callback(self, indata, frames, time_info, status) -> None:
        if status:
            log.debug("Audio status: %s", status)
        try:
            self._queue.put_nowait(bytes(indata))
        except queue.Full:
            # Recognition fell behind. Dropping the oldest block keeps latency
            # bounded rather than transcribing audio from seconds ago.
            self.overflows += 1
            try:
                self._queue.get_nowait()
                self._queue.put_nowait(bytes(indata))
            except queue.Empty:
                pass

    def start(self) -> None:
        self._stream = sd.RawInputStream(
            samplerate=SAMPLE_RATE,
            blocksize=BLOCK_FRAMES,
            device=self.device,
            dtype="int16",
            channels=1,
            callback=self._callback,
        )
        self._stream.start()
        log.info("Microphone open (device=%s)", self.device if self.device is not None else "default")

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception as exc:
                log.warning("Error closing microphone: %s", exc)
            self._stream = None

    def read(self, timeout: float = 1.0) -> bytes | None:
        try:
            return self._queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def drain(self) -> None:
        """Throw away buffered audio -- used after a command runs."""
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                return

    def __enter__(self) -> AudioSource:
        self.start()
        return self

    def __exit__(self, *exc_info) -> None:
        self.stop()
