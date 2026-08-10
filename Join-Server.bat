@echo off
REM Point this PC at the shop server (URL + token).
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\join-server.ps1" %*
pause
