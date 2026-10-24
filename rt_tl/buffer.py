"""Thread-safe rolling audio buffer for sliding-window transcription."""
from __future__ import annotations

import threading
from collections import deque

import numpy as np


class RollingAudioBuffer:
    """Keeps the most recent `window_s` seconds of audio, made of fixed-size blocks.

    `push()` is called from the capture thread; `snapshot()` is called from the
    transcription loop. Both are cheap and lock-protected, so there's no
    meaningful contention at these rates (one push every ~30ms, one snapshot
    every ~1s).
    """

    def __init__(self, block_frames: int):
        self._deque: deque[np.ndarray] = deque(maxlen=block_frames)
        self._lock = threading.Lock()

    def push(self, frame: np.ndarray) -> None:
        with self._lock:
            self._deque.append(frame)

    def snapshot(self) -> np.ndarray:
        with self._lock:
            if not self._deque:
                return np.array([], dtype=np.float32)
            return np.concatenate(list(self._deque))


class GrowingAudioBuffer:
    """Accumulates audio from the start of the current (not-yet-finalized) utterance.

    Unlike `RollingAudioBuffer`, this grows until explicitly `reset()` - used for
    an "active segment" that always starts at the true beginning of an utterance
    (so Whisper never has to guess a word chopped off mid-sound), while still being
    re-transcribed periodically for a live, self-correcting preview.
    """

    def __init__(self):
        self._frames: list[np.ndarray] = []
        self._lock = threading.Lock()

    def push(self, frame: np.ndarray) -> None:
        with self._lock:
            self._frames.append(frame)

    def snapshot(self) -> np.ndarray:
        with self._lock:
            if not self._frames:
                return np.array([], dtype=np.float32)
            return np.concatenate(self._frames)

    def reset(self) -> None:
        with self._lock:
            self._frames = []

    def frame_count(self) -> int:
        with self._lock:
            return len(self._frames)

    def snapshot_tail(self, max_samples: int) -> np.ndarray:
        """Like `snapshot()`, but only concatenates as many trailing frames as
        needed to cover `max_samples` - so preview cost stays bounded even once
        the segment has grown far past that, instead of re-transcribing
        everything from the true start every tick."""
        with self._lock:
            if not self._frames:
                return np.array([], dtype=np.float32)
            collected: list[np.ndarray] = []
            total = 0
            for f in reversed(self._frames):
                collected.append(f)
                total += f.shape[0]
                if total >= max_samples:
                    break
            collected.reverse()
        audio = np.concatenate(collected)
        if audio.shape[0] > max_samples:
            audio = audio[-max_samples:]
        return audio
