@echo off
REM Opt-in client update (keeps config). Double-click or run from the Car-RO folder.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\update-client.ps1" %*
pause
