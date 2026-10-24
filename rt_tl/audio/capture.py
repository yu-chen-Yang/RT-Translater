"""Cross-platform loopback audio capture.

Uses the `soundcard` library, which exposes loopback recording through a single
API on both backends we care about:
  - Windows: WASAPI loopback on the default (or matched) output device.
  - Linux: the PulseAudio/PipeWire "monitor" source of the default (or matched) sink.

This means the same code path works on both OSes without needing a virtual
cable or a Discord bot token - we just listen to whatever is coming out of
the speakers (or a specific app's output device, if the OS routes it there).
"""
from __future__ import annotations

import logging
import threading
from typing import Callable, Optional

import numpy as np
import soundcard as sc

logger = logging.getLogger(__name__)


def find_loopback_device(keyword: Optional[str] = None):
    """Return a loopback-capable microphone object.

    If `keyword` is given, picks the first loopback device whose name contains
    it (case-insensitive) - useful for targeting a specific virtual sink/output
    (e.g. one dedicated to Discord). Otherwise falls back to the default speaker's
    loopback.
    """
    mics = sc.all_microphones(include_loopback=True)
    if keyword:
        kw = keyword.lower()
        for mic in mics:
            if kw in mic.name.lower():
                logger.info("Using loopback device matched by keyword: %s", mic.name)
                return mic
        logger.warning("No loopback device matched keyword %r, falling back to default", keyword)

    default_speaker = sc.default_speaker()
    for mic in mics:
        if mic.name == default_speaker.name:
            logger.info("Using default speaker's loopback: %s", mic.name)
            return mic

    if mics:
        logger.warning("Default speaker loopback not found, using first available: %s", mics[0].name)
        return mics[0]

    raise RuntimeError("No loopback-capable audio device found on this system")


class LoopbackCapture:
    """Streams mono float32 audio frames from the system/application output.

    Runs its own thread; delivers fixed-size blocks to `on_frames` as they
    arrive, resampled/mixed down to `sample_rate` / mono.
    """

    def __init__(
        self,
        on_frames: Callable[[np.ndarray], None],
        sample_rate: int = 16000,
        block_ms: int = 30,
        device_keyword: Optional[str] = None,
    ):
        self._on_frames = on_frames
        self._sample_rate = sample_rate
        self._block_size = int(sample_rate * block_ms / 1000)
        self._device_keyword = device_keyword
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="LoopbackCapture", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def _run(self) -> None:
        mic = find_loopback_device(self._device_keyword)
        try:
            with mic.recorder(samplerate=self._sample_rate, channels=1, blocksize=self._block_size) as rec:
                logger.info(
                    "Loopback capture started: device=%s rate=%d block=%d",
                    mic.name, self._sample_rate, self._block_size,
                )
                while not self._stop_event.is_set():
                    data = rec.record(numframes=self._block_size)
                    mono = data[:, 0] if data.ndim > 1 else data
                    self._on_frames(mono.astype(np.float32))
        except Exception:
            logger.exception("Loopback capture failed")
