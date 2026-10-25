"""Local speech-to-text, fully offline.

Two interchangeable engines:
  - "sensevoice": Alibaba FunASR's SenseVoice-small - generally stronger on
    Mandarin (colloquial speech, noisy/music-heavy backgrounds) than Whisper,
    and the default here for that reason. Built-in language ID, no context
    prompting support.
  - "whisper": faster-whisper (CTranslate2) - supports `initial_prompt`
    context biasing and a range of model sizes; kept as a fallback / for
    non-Chinese-heavy use cases.
"""
from __future__ import annotations

import logging
import os
import re
import sys
from importlib import util as importlib_util
from typing import Optional

logger = logging.getLogger(__name__)


def _register_nvidia_dll_dirs() -> None:
    """On Windows, CTranslate2 looks for cublas64_*.dll / cudnn64_*.dll on PATH or
    in a registered DLL directory. The `nvidia-cublas-cu12` / `nvidia-cudnn-cu12`
    pip packages ship those DLLs under site-packages but don't add them anywhere
    Windows will find - so without this, GPU inference fails with
    "Library cublas64_12.dll is not found" even though the packages are installed.
    """
    if sys.platform != "win32":
        return
    for package, subdir in (
        ("nvidia.cublas", "bin"),
        ("nvidia.cudnn", "bin"),
        ("nvidia.cuda_runtime", "bin"),
    ):
        spec = importlib_util.find_spec(package)
        if spec is None or not spec.submodule_search_locations:
            continue
        for location in spec.submodule_search_locations:
            dll_dir = os.path.join(location, subdir)
            if os.path.isdir(dll_dir):
                os.add_dll_directory(dll_dir)
                # Also prepend to PATH: some other imported library may have called
                # SetDefaultDllDirectories() and locked out add_dll_directory()-registered
                # paths process-wide, but the legacy PATH-based search still works.
                os.environ["PATH"] = dll_dir + os.pathsep + os.environ.get("PATH", "")
                logger.info("Registered DLL directory: %s", dll_dir)


_register_nvidia_dll_dirs()

import numpy as np

# SenseVoice emits a language tag that doesn't always match an ISO code Argos
# understands (e.g. Cantonese); map those to the closest supported code.
_SENSEVOICE_LANG_MAP = {"yue": "zh", "auto": "zh", "nospeech": None}


class SpeechToText:
    def __init__(
        self,
        engine: str = "sensevoice",
        model_size: str = "small",
        device: str = "auto",
        compute_type: str = "int8",
        language: Optional[str] = None,
    ):
        self._engine = engine
        self._language = language

        if engine == "whisper":
            from faster_whisper import WhisperModel
            logger.info("Loading faster-whisper model=%s device=%s compute_type=%s", model_size, device, compute_type)
            self._model = WhisperModel(model_size, device=device, compute_type=compute_type)
        elif engine == "sensevoice":
            self._init_sensevoice(device)
        else:
            raise ValueError(f"Unknown STT engine: {engine!r}")

    def _init_sensevoice(self, device: str) -> None:
        import torch
        from funasr import AutoModel

        if device == "auto":
            resolved = "cuda:0" if torch.cuda.is_available() else "cpu"
        elif device == "cuda":
            resolved = "cuda:0"
        else:
            resolved = device

        logger.info("Loading FunASR SenseVoice-small on device=%s", resolved)
        self._sv_model = AutoModel(model="iic/SenseVoiceSmall", trust_remote_code=True, device=resolved)

    def transcribe(self, audio: np.ndarray, context_prompt: Optional[str] = None) -> Optional[tuple[str, str]]:
        """audio: mono float32 PCM at 16kHz.

        `context_prompt` is the tail of the previous segment's transcript (if
        any). Only the "whisper" engine uses it (as Whisper's initial_prompt,
        biasing decoding toward continuing that sentence/topic); SenseVoice
        has no equivalent and ignores it.

        Returns (text, detected_language_code), or None if the segment had no speech.
        """
        if self._engine == "whisper":
            return self._transcribe_whisper(audio, context_prompt)
        return self._transcribe_sensevoice(audio)

    def _transcribe_whisper(self, audio: np.ndarray, context_prompt: Optional[str]) -> Optional[tuple[str, str]]:
        segments, info = self._model.transcribe(
            audio,
            language=self._language,
            vad_filter=False,  # we already did VAD upstream
            beam_size=1,
            condition_on_previous_text=False,
            initial_prompt=context_prompt,
        )
        text = "".join(seg.text for seg in segments).strip()
        if not text:
            return None
        return text, info.language

    def _transcribe_sensevoice(self, audio: np.ndarray) -> Optional[tuple[str, str]]:
        from funasr.utils.postprocess_utils import rich_transcription_postprocess

        results = self._sv_model.generate(
            input=audio,
            cache={},
            language=self._language or "auto",
            use_itn=True,
            batch_size_s=60,
        )
        if not results:
            return None

        raw = results[0]["text"]
        match = re.search(r"<\|(\w+)\|>", raw)
        lang = _SENSEVOICE_LANG_MAP.get(match.group(1), match.group(1)) if match else "zh"
        if lang is None:  # explicit "no speech" tag
            return None

        text = rich_transcription_postprocess(raw).strip()
        if not text:
            return None
        return text, lang
