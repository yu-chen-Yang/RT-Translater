"""Central configuration for RT-TL."""
from dataclasses import dataclass


@dataclass
class Config:
    # Audio
    sample_rate: int = 16000          # Whisper expects 16kHz mono
    channels: int = 1
    device_keyword: str | None = None  # substring to match a specific output device name
                                        # (e.g. a Discord-specific virtual sink name on Linux),
                                        # None = system default output loopback

    # Preview-then-commit transcription
    audio_block_ms: int = 30           # capture granularity; must be 10/20/30 for webrtcvad
    interval_s: float = 0.5            # how often the in-progress segment is re-previewed
    preview_window_s: float = 4.0      # only the trailing N seconds are re-transcribed for the preview,
                                        # so preview cost stays flat no matter how long the segment has grown
    max_active_s: float = 10.0         # force-commit a segment if it runs this long without a pause
    vad_aggressiveness: int = 2        # webrtcvad 0-3, higher = more aggressive speech filtering
    silence_tail_ms: int = 300         # pause length that commits the current segment

    # STT
    stt_engine: str = "sensevoice"     # "sensevoice" (FunASR, stronger on Mandarin) or "whisper"
    whisper_model: str = "small"       # tiny/base/small/medium/large-v3; small balances speed/accuracy; whisper engine only
    whisper_device: str = "auto"       # "cpu", "cuda", or "auto"; applies to both engines
    whisper_compute_type: str = "int8"  # int8 is fast on CPU, float16 on GPU; whisper engine only
    source_language: str | None = None  # None = auto-detect per segment

    # Translation
    target_language: str = "zh"        # ISO 639-1 code, e.g. "zh", "en", "ja"

    # Overlay UI
    overlay_max_lines: int = 1         # how many past utterances stay visible; 1 = only the latest
    overlay_font_size: int = 20
    overlay_opacity: float = 0.85
    overlay_width: int = 900
    overlay_bottom_margin: int = 80    # px from the bottom edge of the screen
