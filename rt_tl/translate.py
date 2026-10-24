"""Local offline translation via Argos Translate.

Argos ships small language-pair models downloaded once (fully usable offline
afterwards). We auto-install the needed pair on first use so the app works
out of the box as long as it had network access at least once to fetch models
(point `python -m rt_tl.setup_models` at a pair ahead of time for a fully
offline deployment).
"""
from __future__ import annotations

import logging
from typing import Optional

import argostranslate.package
import argostranslate.translate

logger = logging.getLogger(__name__)


def ensure_package(from_code: str, to_code: str) -> bool:
    """Install the from->to language package if not already installed. Returns success."""
    installed = argostranslate.translate.get_installed_languages()
    have_pair = any(
        lang.code == from_code and any(t.to_lang.code == to_code for t in lang.translations_from)
        for lang in installed
    )
    if have_pair:
        return True

    try:
        argostranslate.package.update_package_index()
        available = argostranslate.package.get_available_packages()
        match = next((p for p in available if p.from_code == from_code and p.to_code == to_code), None)
        if match is None:
            logger.error("No Argos package available for %s -> %s", from_code, to_code)
            return False
        path = match.download()
        argostranslate.package.install_from_path(path)
        logger.info("Installed Argos package %s -> %s", from_code, to_code)
        return True
    except Exception:
        logger.exception("Failed to install Argos package %s -> %s", from_code, to_code)
        return False


class Translator:
    def __init__(self, target_language: str = "zh"):
        self._target = target_language
        self._ready_pairs: set[tuple[str, str]] = set()

    def set_target_language(self, target_language: str) -> None:
        self._target = target_language

    def translate(self, text: str, source_language: str) -> Optional[str]:
        if source_language == self._target:
            return text  # nothing to do

        pair = (source_language, self._target)
        if pair not in self._ready_pairs:
            if not ensure_package(*pair):
                return None
            self._ready_pairs.add(pair)

        try:
            return argostranslate.translate.translate(text, source_language, self._target)
        except Exception:
            logger.exception("Translation failed for %s -> %s", source_language, self._target)
            return None
