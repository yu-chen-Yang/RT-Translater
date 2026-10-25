@echo off
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
if not exist logs mkdir logs
pythonw -m rt_tl.main --whisper-device auto --target-language zh > logs\rt_tl.log 2>&1
