@echo off
REM Double-click friendly launcher for the advisor desk GUI.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\run-advisor-ui.ps1" %*
