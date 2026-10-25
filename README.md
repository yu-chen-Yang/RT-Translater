# RT-TL — Real-Time Subtitle Translator

Captures your system/app audio output (e.g. Discord voice), transcribes and translates it fully offline, and shows the result as a floating overlay subtitle on your desktop.

- **Audio capture**: `soundcard` loopback — WASAPI on Windows, PulseAudio/PipeWire monitor on Linux. No virtual cable or Discord bot token needed.
- **Speech recognition**: Alibaba FunASR's `SenseVoice-small` by default (strong on Mandarin, fast on CPU alone), or `faster-whisper` via `--stt-engine whisper`.
- **Translation**: `argostranslate`, offline (downloads a language-pair package once on first use).
- **UI**: a transparent, click-through, always-on-top PyQt6 overlay with a system tray icon.

## Install

```bash
pip install -r requirements.txt
```

On Linux, `soundcard` needs PulseAudio (or PipeWire's pulse-compatible layer) running.

For GPU acceleration with `--stt-engine whisper`, additionally:

```bash
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12   # Windows + NVIDIA GPU
```

## Start / Stop

**Windows**: double-click `start.bat` (runs via `pythonw`, no console window).

**Linux**: `./start.sh` (make it executable first: `chmod +x start.sh`).

Both start the app in the background. Logs go to `logs/rt_tl.log`. To stop, right-click the tray icon (a blue "译" circle) and choose **Quit** — there's no window to close, so this is the only way out besides killing the process. The tray menu also has **Translate to Chinese** / **Translate to English** to switch direction without restarting.

To auto-start on login: add a shortcut to `start.bat` in the Windows Startup folder (`Win+R` → `shell:startup`), or add `start.sh` to your Linux desktop environment's autostart apps / a systemd user service. Neither is set up by default.

To run manually from a terminal instead (useful for seeing logs live):

```bash
python -m rt_tl.main --target-language zh
```

Common flags: `--stt-engine sensevoice|whisper`, `--whisper-device cpu|cuda|auto`, `--target-language zh`, `--device-keyword <substring>` to pin a specific output device.
