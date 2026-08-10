@echo off
REM Double-click this file to install Car-RO on Windows (Technician bay client).
REM Requires Python 3.10+ with "Add python.exe to PATH" checked during setup.
setlocal EnableExtensions
cd /d "%~dp0"

title Car-RO install
echo.
echo  Car-RO Windows install
echo  ======================
echo.
echo  This installs the Technician bay client (CLI).
echo  Unzip folder: %CD%
echo.

if not exist "%~dp0scripts\install.ps1" (
  echo  ERROR: scripts\install.ps1 not found.
  echo  Make sure you unzipped the full Release zip and are running
  echo  Install-Car-RO.bat from the top of that folder.
  echo.
  pause
  exit /b 1
)

where python >nul 2>&1
if errorlevel 1 (
  where py >nul 2>&1
  if errorlevel 1 (
    echo  ERROR: Python not found on PATH.
    echo  Install Python 3.10+ from https://www.python.org/downloads/
    echo  and check "Add python.exe to PATH", then run this again.
    echo.
    pause
    exit /b 1
  )
)

echo  Running scripts\install.ps1 ...
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install.ps1"
set ERR=%ERRORLEVEL%
echo.
if not "%ERR%"=="0" (
  echo  Install failed ^(exit %ERR%^). See messages above.
  pause
  exit /b %ERR%
)

echo.
echo  Next steps:
echo    1. Close this window
echo    2. Open Windows Terminal ^(or a new PowerShell^)
echo    3. Type:  carro
echo.
echo  Shop server join: docs\WINDOWS.md and docs\SERVER_SETUP.md
echo.
pause
endlocal
