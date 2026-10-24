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

## 启动 / 关闭

**Windows**：双击 `start.bat`（内部用 `pythonw` 启动，不会弹黑色命令行窗口）。启动后右下角系统托盘会出现一个蓝色"译"字图标——右键它可以切换翻译方向（译成中文/译成英文），或点"退出"关闭程序。日志写在 `logs/rt_tl.log`。

**Linux**：`./start.sh`（首次需要 `chmod +x start.sh`）。同样是后台启动 + 托盘图标退出，日志在 `logs/rt_tl.log`。

如果想开机自动启动：Windows 把 `start.bat` 的快捷方式放进 `shell:startup`（Win+R 输入这个打开启动文件夹）；Linux 视桌面环境加到自己的自启动应用里，或用 systemd user service。两种都没有默认配置，需要手动加。

手动命令行运行（方便调参/看日志）：

```bash
python -m rt_tl.main --target-language zh
```

常用参数：

- `--device-keyword 关键词`：只监听名字匹配该关键词的输出设备（比如你给 Discord 单独配了一个虚拟输出 sink/设备，可以按名字锁定）。
- `--source-language en`：强制源语言，不填则按段自动检测。
- `--target-language zh`：启动时的默认目标语言（ISO 639-1，如 zh/en/ja/ko），运行中可以用托盘菜单切换 zh/en。
- `--whisper-model small`：tiny/base/small/medium/large-v3，模型越大越准但越慢。
- `--whisper-device cpu|cuda|auto`：有 NVIDIA GPU 建议 `cuda` 提速（Windows 下需要先 `pip install nvidia-cublas-cu12 nvidia-cudnn-cu12`，代码会自动把这两个包的 DLL 目录加进 PATH）。
- `--interval-s` / `--preview-window-s` / `--max-active-s`：调实时性与准确度的三个旋钮，见下方架构说明。

## 架构

**预览-定稿（preview-then-commit）模式**：当前这句话从真正开头持续累积音频，每 `interval_s` 秒重新转写一次最近 `preview_window_s` 秒作为"实时预览行"（会不断自我修正），检测到停顿（`silence_tail_ms`）或说太久撞到 `max_active_s` 上限时，用这句话从头到尾的完整音频重新转写一次，定稿成不再变化的"历史行"，随后开始下一句。

```
系统/应用输出(loopback) → 30ms音频块 → 累积缓冲区(buffer.py)
                                    ├─ 停顿检测(vad.py: PauseTrigger) → 触发定稿
                                    └─ 每隔interval_s秒 → 取最近preview_window_s秒 → 预览转写 → 悬浮窗"实时行"
   定稿时 → 取完整音频 → 转写(语种检测) → 翻译 → 悬浮窗"历史行" → 开始下一句
```

- `rt_tl/audio/capture.py`：跨平台 loopback 采集线程。
- `rt_tl/buffer.py`：当前这句话的音频缓冲区（支持只取尾部一段做预览，避免越说越长转写越慢）。
- `rt_tl/vad.py`：`PauseTrigger`，检测说话人停顿，用来提前触发定稿（而不是死等固定间隔）。
- `rt_tl/stt.py`：faster-whisper 封装，支持用上一句定稿文字做 `initial_prompt` 提升连贯性；Windows 下负责把 cuBLAS/cuDNN 的 DLL 目录注册进 PATH。
- `rt_tl/translate.py`：argostranslate 封装，按需自动装语言包，支持运行时切换目标语言。
- `rt_tl/overlay.py`：PyQt6 悬浮字幕窗口 + 系统托盘图标；线程安全（`push_live()`/`commit_live()` 用 Qt signal 跨线程更新 UI），窗口随内容高度自适应、水平居中贴底部、鼠标可穿透。
- `rt_tl/pipeline.py`：把以上串起来，STT/翻译跑在独立 worker 线程，不阻塞音频采集。

## 已知限制 / 后续可做

- 默认监听"默认输出设备"的 loopback，也就是能听到系统放出来的所有声音（包括 Discord）。如果想只听 Discord，Windows 上可以把 Discord 的"应用音量和设备首选项"单独指到一个虚拟输出设备，再用 `--device-keyword` 锁定；Linux 下可以用 `pavucontrol` 把 Discord 的 sink-input 挪到专门的 sink。
- 多说话人目前不区分说话人（没有 diarization）。
- 翻译质量取决于 argostranslate 对应语言对模型的质量，某些生僻语言对可能没有直接模型。
