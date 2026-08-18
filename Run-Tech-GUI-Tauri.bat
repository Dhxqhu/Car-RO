@echo off
REM Double-click friendly launcher for Tauri tech GUI (dev).
cd /d "%~dp0"
if exist "%ProgramFiles%\nodejs\node.exe" set "PATH=%ProgramFiles%\nodejs;%APPDATA%\npm;%PATH%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run-gui-tauri.ps1" %*
if errorlevel 1 (
  echo.
  echo  Tauri GUI failed to start. See the error above.
  pause
)
