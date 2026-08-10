@echo off
REM Double-click friendly launcher for the tech GUI (Vite + engine).
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run-gui-dev.ps1" %*
