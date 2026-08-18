@echo off
REM Double-click friendly launcher for the advisor desk GUI.
cd /d "%~dp0"
if exist "%ProgramFiles%\nodejs\node.exe" set "PATH=%ProgramFiles%\nodejs;%APPDATA%\npm;%PATH%"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run-advisor-ui.ps1" %*
if errorlevel 1 (
  echo.
  echo  Advisor GUI failed to start. See the error above.
  pause
)
