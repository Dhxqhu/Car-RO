# Point this Windows bay/advisor PC at an existing carro-server (URL + token).
# Parity with scripts/join-server.sh
#
#   .\scripts\join-server.ps1

$ErrorActionPreference = "Stop"

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $Root

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
  Write-Error "error: run Install-Car-RO.bat / .\scripts\install.ps1 first (need .venv)"
}

$env:PYTHONPATH = (@(
  (Join-Path $Root "cli"),
  (Join-Path $Root "server"),
  (Join-Path $Root "engine")
) -join ";")

Write-Host "=============================================="
Write-Host "  Join an existing Car-RO server (bay PC)"
Write-Host "=============================================="
Write-Host ""
Write-Host "Use the URL + token from the server install output"
Write-Host "(or on the server: grep CARRO_TOKEN ~/.config/carro-server.env)."
Write-Host ""
Write-Host "This is the shop API token — the same value on every bay PC."
Write-Host "Do not generate a new token on this laptop unless you also"
Write-Host "changed CARRO_TOKEN on the server (see docs\SERVER_SETUP.md)."
Write-Host ""

$URL = Read-Host "Server URL (e.g. http://homebaseserver:8787)"
$URL = ($URL -replace '\s+', '').TrimEnd('/')
if (-not $URL) {
  Write-Error "URL required"
}

$TOKEN = Read-Host "API token"
$TOKEN = ($TOKEN -replace '\s+', '')
if (-not $TOKEN) {
  Write-Error "token required"
}

& $VenvPython -m carro config set server_url $URL
& $VenvPython -m carro config set token $TOKEN
Write-Host "==> Syncing…"
& $VenvPython -m carro sync
Write-Host ""
Write-Host "Done. Config kept at $env:USERPROFILE\.config\carro\config.toml"
Write-Host "  carro --version"
Write-Host "  carro sync"
