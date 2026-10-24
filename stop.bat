@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\stop-hidden.ps1"
if %errorlevel%==0 (echo stopped.) else (echo some processes may still be running.)
timeout /t 2 >nul
