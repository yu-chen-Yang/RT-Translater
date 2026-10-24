# RT-TL — 实时语音翻译悬浮字幕

捕获系统/应用输出音轨（如 Discord 语音），本地离线做语音识别 + 翻译，结果以悬浮透明字幕显示在桌面上。

全链路离线、跨平台（Windows / Linux）：

- **音频捕获**：`soundcard` 库的 loopback 录音 — Windows 下走 WASAPI loopback，Linux 下走 PulseAudio/PipeWire 的 monitor source。不需要虚拟声卡，也不需要 Discord Bot token，直接监听系统/默认输出设备（或用 `--device-keyword` 匹配特定虚拟 sink）。
- **语音识别**：`faster-whisper`（CTranslate2），本地推理，支持自动语种检测。
- **翻译**：`argostranslate`，本地离线翻译模型（首次用到某个语言对时会自动下载安装一次，之后完全离线）。
- **界面**：PyQt6 做的置顶透明悬浮窗，滚动显示「原文 + 译文」。

## 安装

```bash
pip install -r requirements.txt
```

Linux 下 `soundcard` 依赖 PulseAudio（或兼容的 PipeWire-pulse），确保系统已启用。

## 运行

```bash
python -m rt_tl.main --target-language zh
```

常用参数：

- `--device-keyword 关键词`：只监听名字匹配该关键词的输出设备（比如你给 Discord 单独配了一个虚拟输出 sink/设备，可以按名字锁定）。
- `--source-language en`：强制源语言，不填则按段自动检测。
- `--target-language zh`：目标语言（ISO 639-1，如 zh/en/ja/ko）。
- `--whisper-model small`：tiny/base/small/medium/large-v3，模型越大越准但越慢。
- `--whisper-device cpu|cuda|auto`：有 NVIDIA GPU 建议 `cuda` 提速。

## 架构

```
系统/应用输出(loopback) → 30ms音频块 → VAD分段(webrtcvad)
    → 完整语句片段 → 队列 → [faster-whisper 转写 + 语种检测]
    → [argostranslate 翻译] → 悬浮窗 push(原文, 译文)
```

- `rt_tl/audio/capture.py`：跨平台 loopback 采集线程。
- `rt_tl/vad.py`：基于 webrtcvad 的分段器，把连续音频切成一句句话。
- `rt_tl/stt.py`：faster-whisper 封装。
- `rt_tl/translate.py`：argostranslate 封装，按需自动装语言包。
- `rt_tl/overlay.py`：PyQt6 悬浮字幕窗口，线程安全（`push()` 用 Qt signal 跨线程更新 UI）。
- `rt_tl/pipeline.py`：把以上串起来，STT/翻译跑在独立 worker 线程，不阻塞音频采集。

## 已知限制 / 后续可做

- 默认监听"默认输出设备"的 loopback，也就是能听到系统放出来的所有声音（包括 Discord）。如果想只听 Discord，Windows 上可以把 Discord 的"应用音量和设备首选项"单独指到一个虚拟输出设备，再用 `--device-keyword` 锁定；Linux 下可以用 `pavucontrol` 把 Discord 的 sink-input 挪到专门的 sink。
- 多说话人目前不区分说话人（没有 diarization）。
- 翻译质量取决于 argostranslate 对应语言对模型的质量，某些生僻语言对可能没有直接模型。
