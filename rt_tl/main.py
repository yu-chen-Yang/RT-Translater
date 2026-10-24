"""Entry point: launches the overlay UI and starts the audio pipeline."""
from __future__ import annotations

import argparse
import logging

from PyQt6.QtGui import QActionGroup

from .config import Config
from .overlay import run_overlay_app
from .pipeline import Pipeline


def parse_args() -> Config:
    config = Config()
    p = argparse.ArgumentParser(description="Real-time desktop subtitle translator")
    p.add_argument("--device-keyword", default=config.device_keyword,
                    help="substring to match a specific output device for loopback capture")
    p.add_argument("--source-language", default=config.source_language,
                    help="force source language code (default: auto-detect)")
    p.add_argument("--target-language", default=config.target_language,
                    help="translation target language code, e.g. zh/en/ja")
    p.add_argument("--whisper-model", default=config.whisper_model,
                    help="faster-whisper model size: tiny/base/small/medium/large-v3")
    p.add_argument("--whisper-device", default=config.whisper_device, help="cpu/cuda/auto")
    p.add_argument("--overlay-width", type=int, default=config.overlay_width, help="overlay window width")
    p.add_argument("--overlay-bottom-margin", type=int, default=config.overlay_bottom_margin,
                    help="px from the bottom edge of the screen")
    p.add_argument("--overlay-max-lines", type=int, default=config.overlay_max_lines,
                    help="how many past utterances stay visible; 1 = only the latest")
    p.add_argument("--interval-s", type=float, default=config.interval_s,
                    help="how often the in-progress segment is re-previewed")
    p.add_argument("--preview-window-s", type=float, default=config.preview_window_s,
                    help="only the trailing N seconds are re-transcribed for the preview")
    p.add_argument("--max-active-s", type=float, default=config.max_active_s,
                    help="force-commit a segment if it runs this long without a pause")
    args = p.parse_args()

    config.device_keyword = args.device_keyword
    config.source_language = args.source_language
    config.target_language = args.target_language
    config.whisper_model = args.whisper_model
    config.whisper_device = args.whisper_device
    config.overlay_width = args.overlay_width
    config.overlay_bottom_margin = args.overlay_bottom_margin
    config.overlay_max_lines = args.overlay_max_lines
    config.interval_s = args.interval_s
    config.preview_window_s = args.preview_window_s
    config.max_active_s = args.max_active_s
    return config


def _add_direction_toggle(overlay, pipeline, initial_target: str) -> None:
    """Adds "译成中文" / "译成英文" checkable options to the tray menu, letting the
    translation direction be flipped at runtime without restarting the app."""
    group = QActionGroup(overlay.tray_menu)
    group.setExclusive(True)

    to_zh = overlay.tray_menu.addAction("Translate to Chinese")
    to_en = overlay.tray_menu.addAction("Translate to English")
    for action, lang in ((to_zh, "zh"), (to_en, "en")):
        action.setCheckable(True)
        action.setChecked(lang == initial_target)
        group.addAction(action)
        action.triggered.connect(lambda checked, lang=lang: pipeline.set_target_language(lang))


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = parse_args()

    pipeline_holder: dict = {}

    def on_overlay_ready(overlay) -> None:
        pipeline = Pipeline(config, overlay)
        pipeline_holder["pipeline"] = pipeline
        pipeline.start()
        _add_direction_toggle(overlay, pipeline, config.target_language)

    try:
        run_overlay_app(
            on_overlay_ready,
            max_lines=config.overlay_max_lines,
            font_size=config.overlay_font_size,
            opacity=config.overlay_opacity,
            width=config.overlay_width,
            bottom_margin=config.overlay_bottom_margin,
        )
    finally:
        pipeline = pipeline_holder.get("pipeline")
        if pipeline is not None:
            pipeline.stop()


if __name__ == "__main__":
    main()
