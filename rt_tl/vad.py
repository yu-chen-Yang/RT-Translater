"""Pause detection: fires a callback shortly after speech drops into silence.

Used to wake the sliding-window transcriber early (instead of waiting for the
next scheduled tick) so sentence ends feel responsive, while the fixed-interval
tick still covers long, pause-free speech.
"""
from __future__ import annotations

from typing import Callable

import numpy as np
import webrtcvad


class PauseTrigger:
    def __init__(
        self,
        on_pause: Callable[[], None],
        sample_rate: int = 16000,
        frame_ms: int = 30,
        aggressiveness: int = 2,
        silence_tail_ms: int = 300,
    ):
        self._on_pause = on_pause
        self._sample_rate = sample_rate
        self._frame_samples = int(sample_rate * frame_ms / 1000)
        self._vad = webrtcvad.Vad(aggressiveness)
        self._silence_tail_frames = max(1, silence_tail_ms // frame_ms)

        self._had_speech = False
        self._silence_run = 0

    def push(self, frame: np.ndarray) -> None:
        if frame.shape[0] != self._frame_samples:
            return

        if self._is_speech(frame):
            self._had_speech = True
            self._silence_run = 0
            return

        if not self._had_speech:
            return

        self._silence_run += 1
        if self._silence_run >= self._silence_tail_frames:
            self._had_speech = False
            self._silence_run = 0
            self._on_pause()

    def _is_speech(self, frame: np.ndarray) -> bool:
        pcm16 = np.clip(frame * 32768.0, -32768, 32767).astype(np.int16).tobytes()
        try:
            return self._vad.is_speech(pcm16, self._sample_rate)
        except Exception:
            return False
