@echo off
cd /d "%~dp0"
set PYTHONPATH=src
.venv\Scripts\python.exe -m qqbot.main
pause
