"""Local speech-to-text via faster-whisper (CTranslate2, fully offline)."""
from __future__ import annotations

import logging
import os
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
from faster_whisper import WhisperModel


class SpeechToText:
    def __init__(
        self,
        model_size: str = "small",
        device: str = "auto",
        compute_type: str = "int8",
        language: Optional[str] = None,
    ):
        self._language = language
        logger.info("Loading faster-whisper model=%s device=%s compute_type=%s", model_size, device, compute_type)
        self._model = WhisperModel(model_size, device=device, compute_type=compute_type)

    def transcribe(self, audio: np.ndarray, context_prompt: Optional[str] = None) -> Optional[tuple[str, str]]:
        """audio: mono float32 PCM at 16kHz.

        `context_prompt` is the tail of the previous segment's transcript (if any);
        passing it as Whisper's initial_prompt biases decoding toward continuing that
        same sentence/topic, which helps a lot on short, otherwise ambiguous segments.

        Returns (text, detected_language_code), or None if the segment had no speech.
        """
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
