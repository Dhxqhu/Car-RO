@echo off
REM Double-click friendly launcher for the tech GUI (Vite + engine).
cd /d "%~dp0"
if exist "%ProgramFiles%\nodejs\node.exe" set "PATH=%ProgramFiles%\nodejs;%APPDATA%\npm;%PATH%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run-gui-dev.ps1" %*
if errorlevel 1 (
  echo.
  echo  GUI failed to start. See the error above.
  pause
)
