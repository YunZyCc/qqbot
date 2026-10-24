@echo off
setlocal
cd /d "%~dp0"

echo Starting NapCat + qqbot...
echo.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\start-hidden.ps1"

echo.
echo Done. qqbot runs hidden, NapCat is minimized.
echo   logs : D:\dev\qq-ai-bot\data\qqbot.log
echo   webui: http://127.0.0.1:6099/webui
echo.
echo This window closes in 4 seconds.
timeout /t 4 >nul
