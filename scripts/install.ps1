# Install Car-RO CLI on Windows (venv + carro on User PATH).
#
# Easiest: double-click Install-Car-RO.bat in the repo root.
# Or from PowerShell in the unzipped folder:
#   Set-ExecutionPolicy -Scope Process Bypass
#   .\scripts\install.ps1

$ErrorActionPreference = "Stop"

$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

Write-Host "==> Car-RO install from $Root"

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) {
    $py = Get-Command py -ErrorAction SilentlyContinue
}
if (-not $py) {
    Write-Error "Python not found. Install Python 3.10+ from https://www.python.org/downloads/ and check 'Add python.exe to PATH'."
}

$PyExe = $py.Source
if ($py.Name -eq "py.exe" -or $py.Name -eq "py") {
    $PyExe = "py"
    $PyArgs = @("-3")
} else {
    $PyArgs = @()
}

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "==> Creating .venv"
    & $PyExe @PyArgs -m venv (Join-Path $Root ".venv")
}

$Pip = Join-Path $Root ".venv\Scripts\pip.exe"
Write-Host "==> Installing Python dependencies"
& $Pip install -U pip
& $Pip install -r (Join-Path $Root "requirements.txt")

# Launcher bat on User PATH
$BinDir = Join-Path $env:LOCALAPPDATA "Car-RO\bin"
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
$Bat = Join-Path $BinDir "carro.bat"
$AdvisorBat = Join-Path $BinDir "carroadviser.bat"
$VenvCarro = Join-Path $Root ".venv\Scripts\python.exe"
@"
@echo off
set PYTHONPATH=$Root\cli;$Root\server;$Root\engine
"$VenvCarro" -m carro %*
"@ | Set-Content -Path $Bat -Encoding ASCII
@"
@echo off
set PYTHONPATH=$Root\cli;$Root\server;$Root\engine
"$VenvCarro" -m carro advisor %*
"@ | Set-Content -Path $AdvisorBat -Encoding ASCII

# Also drop helpers next to the repo
$LocalBat = Join-Path $Root "carro.bat"
$LocalAdvisorBat = Join-Path $Root "carroadviser.bat"
@"
@echo off
set PYTHONPATH=$Root\cli;$Root\server;$Root\engine
"$VenvCarro" -m carro %*
"@ | Set-Content -Path $LocalBat -Encoding ASCII
@"
@echo off
set PYTHONPATH=$Root\cli;$Root\server;$Root\engine
"$VenvCarro" -m carro advisor %*
"@ | Set-Content -Path $LocalAdvisorBat -Encoding ASCII

Write-Host "==> Wrote $Bat"
Write-Host "==> Wrote $AdvisorBat"

# User PATH
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not $userPath) { $userPath = "" }
$parts = $userPath -split ";" | Where-Object { $_ -ne "" }
if ($parts -notcontains $BinDir) {
    $newPath = if ($userPath) { "$userPath;$BinDir" } else { $BinDir }
    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
    $env:Path = "$env:Path;$BinDir"
    Write-Host "==> Added $BinDir to your User PATH (reopen terminal)"
} else {
    Write-Host "==> PATH already includes $BinDir"
}

# Config stub
$ConfigDir = Join-Path $env:USERPROFILE ".config\carro"
New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
$ConfigFile = Join-Path $ConfigDir "config.toml"
$Example = Join-Path $Root "config.example.toml"
if (-not (Test-Path $ConfigFile)) {
    Copy-Item $Example $ConfigFile
    Write-Host "==> Wrote $ConfigFile"
} else {
    Write-Host "==> Keeping existing $ConfigFile"
}

$DocRoot = Join-Path $env:USERPROFILE "Documents\Car-RO"
New-Item -ItemType Directory -Force -Path (Join-Path $DocRoot "photos") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $DocRoot "inbox") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $DocRoot "branding") | Out-Null

$env:PYTHONPATH = "$Root\cli;$Root\server;$Root\engine"
& $VenvCarro -m carro config init 2>$null | Out-Null

Write-Host ""
Write-Host "Done. Reopen Windows Terminal, then:"
Write-Host "  carro"
Write-Host "  carro config"
Write-Host "  carroadviser          # advisor desk CLI"
Write-Host ""
Write-Host "Join shop server: see docs\SERVER_SETUP.md and docs\WINDOWS.md"
Write-Host "  carro config set server_url http://YOUR_SERVER:8787"
Write-Host "  carro config set token YOUR_TOKEN"
Write-Host "  carro sync"
