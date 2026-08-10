@echo off
REM Double-click friendly launcher for Tauri tech GUI (dev).
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run-gui-tauri.ps1" %*
