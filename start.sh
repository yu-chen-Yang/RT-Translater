#!/bin/bash
# Linux launcher: starts RT-TL in the background, detached from the terminal.
cd "$(dirname "$0")"
mkdir -p logs
nohup python3 -m rt_tl.main --whisper-device auto --target-language zh \
    > logs/rt_tl.log 2>&1 &
disown
echo "Started (pid $!). Use the tray icon to quit, or: pkill -f rt_tl.main"
