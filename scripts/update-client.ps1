# Opt-in refresh of this Windows bay / advisor PC.
# Keeps %USERPROFILE%\.config\carro\config.toml. Does not touch the shop server.
#
# From the unzipped / git checkout:
#   .\scripts\update-client.ps1
# Or double-click Update-Car-RO.bat in the repo root.

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

function Read-Ver([string]$Path) {
  if (Test-Path $Path) {
    $line = Get-Content -Path $Path -TotalCount 1 -Encoding UTF8
    return ($line -replace '^\uFEFF', '' -replace '^\s+|\s+$', '')
  }
  return "unknown"
}

function Write-CarroBat([string]$OutPath, [string]$ExtraArgs) {
  $VenvCarro = Join-Path $Root ".venv\Scripts\python.exe"
  if ($ExtraArgs) {
    $runLine = "`"$VenvCarro`" -m carro $ExtraArgs %*"
  } else {
    $runLine = "`"$VenvCarro`" -m carro %*"
  }
  $content = @"
@echo off
set PYTHONPATH=$Root\cli;$Root\server;$Root\engine
$runLine
"@
  Set-Content -Path $OutPath -Value $content -Encoding ASCII
}

$Before = Read-Ver (Join-Path $Root "VERSION")
Write-Host "==> Updating Car-RO client at $Root"
Write-Host "    VERSION: $Before"

$ConfigDir = Join-Path $env:USERPROFILE ".config\carro"
$ConfigFile = Join-Path $ConfigDir "config.toml"
if (Test-Path $ConfigFile) {
  Write-Host "    config: $ConfigFile (kept)"
} else {
  Write-Host "    note: no config.toml yet - run Install-Car-RO.bat / install.ps1 on a new PC"
}

$py = Get-Command python -ErrorAction SilentlyContinue
if (-not $py) { $py = Get-Command py -ErrorAction SilentlyContinue }
if (-not $py) {
  Write-Error "Python not found. Install Python 3.10+ and check 'Add python.exe to PATH'."
}
$PyExe = $py.Source
$PyArgs = @()
if ($py.Name -eq "py.exe" -or $py.Name -eq "py") {
  $PyExe = "py"
  $PyArgs = @("-3")
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

# Refresh PATH launchers (parity with install.ps1)
$BinDir = Join-Path $env:LOCALAPPDATA "Car-RO\bin"
New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
Write-CarroBat (Join-Path $BinDir "carro.bat") ""
Write-CarroBat (Join-Path $BinDir "carroadviser.bat") "advisor"
Write-CarroBat (Join-Path $Root "carro.bat") ""
Write-CarroBat (Join-Path $Root "carroadviser.bat") "advisor"
Write-Host "==> Refreshed carro.bat / carroadviser.bat launchers"

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if (-not $userPath) { $userPath = "" }
$parts = $userPath -split ";" | Where-Object { $_ -ne "" }
if ($parts -notcontains $BinDir) {
  $newPath = if ($userPath) { "$userPath;$BinDir" } else { "$BinDir" }
  [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
  $env:Path = "$env:Path;$BinDir"
  Write-Host "==> Added $BinDir to User PATH (reopen terminal)"
}

$GuiUi = Join-Path $Root "gui\ui"
$AdvUi = Join-Path $Root "advisor\ui"
if ((Test-Path (Join-Path $GuiUi "node_modules")) -or $env:CARRO_UPDATE_UI -eq "1") {
  if (Test-Path $GuiUi) {
    Write-Host "==> npm install (tech GUI)"
    Push-Location $GuiUi
    npm install
    Pop-Location
  }
}
if ((Test-Path (Join-Path $AdvUi "node_modules")) -or $env:CARRO_UPDATE_UI -eq "1") {
  if (Test-Path $AdvUi) {
    Write-Host "==> npm install (advisor GUI)"
    Push-Location $AdvUi
    npm install
    Pop-Location
  }
}

$After = Read-Ver (Join-Path $Root "VERSION")
Write-Host ""
Write-Host "Done. Client VERSION: $After"
Write-Host "  carro --version"
Write-Host "Restart engine + GUI if they were running:"
Write-Host "  Run-Tech-GUI.bat    /  .\scripts\run-gui-dev.ps1"
Write-Host "  Run-Advisor-GUI.bat /  .\scripts\run-advisor-ui.ps1"
Write-Host "Update Linux carro-server first when this build needs a newer shop API (docs\UPDATING.md)."
