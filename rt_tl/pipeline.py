"""Wires capture -> active segment buffer -> STT -> translation -> overlay together.

Preview-then-commit transcription: audio for the utterance in progress
accumulates in a buffer that always starts at the true beginning of that
utterance (never mid-word), and gets re-transcribed every `interval_s`
seconds as a live, self-correcting preview. When `PauseTrigger` detects the
speaker paused (or the segment hits a hard duration cap), that preview is
finalized - pushed into the overlay's stable history line - and a fresh
segment starts from the next frame.

This fixes two things a plain fixed-size sliding window has: (1) each
transcription always sees a whole utterance from its real start, so Whisper
isn't guessing a word chopped off at an arbitrary window edge, and (2) the
previous utterance's text visibly settles instead of being silently replaced
by the next arbitrary window's guess.
"""
from __future__ import annotations

import logging
import threading

import numpy as np

from .audio.capture import LoopbackCapture
from .buffer import GrowingAudioBuffer
from .config import Config
from .stt import SpeechToText
from .translate import Translator
from .vad import PauseTrigger

logger = logging.getLogger(__name__)

_SILENCE_RMS_THRESHOLD = 0.003  # skip transcribing windows that are essentially silent


class Pipeline:
    def __init__(self, config: Config, overlay):
        self._config = config
        self._overlay = overlay

        self._stt = SpeechToText(
            engine=config.stt_engine,
            model_size=config.whisper_model,
            device=config.whisper_device,
            compute_type=config.whisper_compute_type,
            language=config.source_language,
        )
        self._translator = Translator(target_language=config.target_language)

        self._buffer = GrowingAudioBuffer()
        self._context_prompt: str | None = None  # tail of the last committed transcript
        self._preview_max_samples = max(1, int(config.preview_window_s * config.sample_rate))

        self._commit_flag = threading.Event()
        self._max_active_frames = max(1, int(config.max_active_s * 1000 / config.audio_block_ms))

        self._pause_trigger = PauseTrigger(
            on_pause=self._commit_flag.set,
            sample_rate=config.sample_rate,
            frame_ms=config.audio_block_ms,
            aggressiveness=config.vad_aggressiveness,
            silence_tail_ms=config.silence_tail_ms,
        )

        def on_frames(frame: np.ndarray) -> None:
            self._buffer.push(frame)
            self._pause_trigger.push(frame)
            if self._buffer.frame_count() >= self._max_active_frames:
                self._commit_flag.set()

        self._capture = LoopbackCapture(
            on_frames=on_frames,
            sample_rate=config.sample_rate,
            block_ms=config.audio_block_ms,
            device_keyword=config.device_keyword,
        )

        self._stop_event = threading.Event()
        self._worker_thread: threading.Thread | None = None

    def start(self) -> None:
        self._stop_event.clear()
        self._worker_thread = threading.Thread(target=self._worker_loop, name="STTWorker", daemon=True)
        self._worker_thread.start()
        self._capture.start()
        logger.info(
            "Pipeline started (interval=%.1fs, max segment=%.1fs, pause trigger=%dms)",
            self._config.interval_s, self._config.max_active_s, self._config.silence_tail_ms,
        )

    def set_target_language(self, target_language: str) -> None:
        """Switches translation direction on the fly (e.g. zh<->en), callable from
        the UI thread while the pipeline is running. Drops whatever utterance was
        in progress, since its context prompt and any partial text were biased
        toward the old direction."""
        self._translator.set_target_language(target_language)
        self._context_prompt = None
        self._buffer.reset()
        self._commit_flag.clear()
        self._overlay.clear_all()
        logger.info("Translation target language switched to %s", target_language)

    def stop(self) -> None:
        self._capture.stop()
        self._stop_event.set()
        self._commit_flag.set()
        if self._worker_thread is not None:
            self._worker_thread.join(timeout=5.0)
        logger.info("Pipeline stopped")

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            committed = self._commit_flag.wait(timeout=self._config.interval_s)
            if self._stop_event.is_set():
                break
            if committed:
                self._commit_flag.clear()
                self._finalize_segment()
            else:
                self._preview_segment()

    def _transcribe(self, audio: np.ndarray):
        if audio.size == 0:
            return None
        rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
        if rms < _SILENCE_RMS_THRESHOLD:
            return None
        return self._stt.transcribe(audio, context_prompt=self._context_prompt)

    def _preview_segment(self) -> None:
        try:
            audio = self._buffer.snapshot_tail(self._preview_max_samples)
            result = self._transcribe(audio)
            if result is None:
                return
            text, detected_lang = result
            logger.info("preview [%s]: %s", detected_lang, text)
            translated = self._translator.translate(text, detected_lang) or text
            self._overlay.push_live(text, translated)
        except Exception:
            logger.exception("Error previewing segment")

    def _finalize_segment(self) -> None:
        audio = self._buffer.snapshot()
        self._buffer.reset()
        try:
            result = self._transcribe(audio)
            if result is None:
                self._overlay.clear_live()
                return
            text, detected_lang = result
            logger.info("commit [%s]: %s", detected_lang, text)
            self._context_prompt = text[-200:]
            translated = self._translator.translate(text, detected_lang) or text
            self._overlay.commit_live(text, translated)
        except Exception:
            logger.exception("Error finalizing segment")
