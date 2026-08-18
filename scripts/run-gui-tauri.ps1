# Launch Tauri tech GUI with local Python engine (dev).
# Usage:
#   .\scripts\run-gui-tauri.ps1
#   .\scripts\run-gui-tauri.ps1 -Scanner
param(
  [switch]$Scanner
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
. (Join-Path $PSScriptRoot "lib\Ensure-Node.ps1")
$env:CARRO_ROOT = "$Root"
$env:PYTHONPATH = (@(
  (Join-Path $Root "cli"),
  (Join-Path $Root "server"),
  (Join-Path $Root "engine")
) -join ";") + $(if ($env:PYTHONPATH) { ";$env:PYTHONPATH" } else { "" })

. (Join-Path $PSScriptRoot "lib\Pick-Port.ps1")

$CargoBin = Join-Path $env:USERPROFILE ".cargo\bin"
if (Test-Path $CargoBin) {
  $env:PATH = "$CargoBin;$env:PATH"
}

$Obd = Join-Path (Split-Path $Root -Parent) "obdscan"
if (Test-Path $Obd) {
  if (-not $env:OBDSCAN_ROOT) { $env:OBDSCAN_ROOT = $Obd }
}

if ($Scanner) { $env:VITE_CARRO_MODE = "scanner" }

$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
  Write-Error "error: run .\scripts\install.ps1 (or Install-Car-RO.bat) first"
}

$Port = Resolve-CarroEnginePort
$engine = $null
if (Test-CarroPortHealthy -Port $Port) {
  Write-Host "==> Engine already on http://127.0.0.1:$Port"
} else {
  Write-Host "==> Engine on http://127.0.0.1:$Port"
  $engine = Start-Process -FilePath $Py -ArgumentList @(
    "-m", "uvicorn", "carro_engine.main:app",
    "--host", "127.0.0.1", "--port", "$Port", "--no-access-log"
  ) -PassThru -NoNewWindow -WorkingDirectory $Root
  Start-Sleep -Milliseconds 500
}

try {
  Set-Location (Join-Path $Root "gui")
  if (-not (Test-Path "node_modules")) { npm install }
  if (-not (Test-Path "ui\node_modules")) { npm --prefix ui install }
  npm run tauri:dev
} finally {
  if ($engine -and -not $engine.HasExited) {
    Stop-Process -Id $engine.Id -Force -ErrorAction SilentlyContinue
  }
}
