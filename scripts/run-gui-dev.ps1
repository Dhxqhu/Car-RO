# Start local engine + Vite tech UI (Windows).
# Usage:
#   .\scripts\run-gui-dev.ps1
#   .\scripts\run-gui-dev.ps1 -Scanner
param(
  [switch]$Scanner
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

$env:PYTHONPATH = (@(
  (Join-Path $Root "cli"),
  (Join-Path $Root "server"),
  (Join-Path $Root "engine")
) -join ";") + $(if ($env:PYTHONPATH) { ";$env:PYTHONPATH" } else { "" })

$Obd = Join-Path (Split-Path $Root -Parent) "obdscan"
if (Test-Path $Obd) {
  if (-not $env:OBDSCAN_ROOT) { $env:OBDSCAN_ROOT = $Obd }
}

$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
  Write-Error "error: run .\scripts\install.ps1 (or Install-Car-RO.bat) first"
}

$Port = if ($env:CARRO_ENGINE_PORT) { $env:CARRO_ENGINE_PORT } else { "8788" }
Write-Host "==> Engine on http://127.0.0.1:$Port"
$engine = Start-Process -FilePath $Py -ArgumentList @(
  "-m", "uvicorn", "carro_engine.main:app",
  "--host", "127.0.0.1", "--port", $Port
) -PassThru -NoNewWindow -WorkingDirectory $Root

try {
  Set-Location (Join-Path $Root "gui\ui")
  if (-not (Test-Path "node_modules")) { npm install }
  if ($Scanner) {
    $env:VITE_CARRO_MODE = "scanner"
    Write-Host "==> UI (scanner-only) on http://127.0.0.1:1420/?mode=scanner"
  } else {
    Remove-Item Env:VITE_CARRO_MODE -ErrorAction SilentlyContinue
    Write-Host "==> UI on http://127.0.0.1:1420 (proxies /api → engine)"
  }
  npm run dev
} finally {
  if ($engine -and -not $engine.HasExited) {
    Stop-Process -Id $engine.Id -Force -ErrorAction SilentlyContinue
  }
}
