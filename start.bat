@echo off
cd /d "%~dp0"
set PYTHONIOENCODING=utf-8
if not exist logs mkdir logs
pythonw -m rt_tl.main --whisper-model small --whisper-device cuda --target-language zh > logs\rt_tl.log 2>&1
