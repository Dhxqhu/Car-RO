# Dev launcher for Car-RO Advisor desk UI (starts local engine if needed).
# Usage: .\scripts\run-advisor-ui.ps1
$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $Root

. (Join-Path $PSScriptRoot "lib\Ensure-Node.ps1")
. (Join-Path $PSScriptRoot "lib\Pick-Port.ps1")

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

$Port = Resolve-CarroEnginePort
$engine = $null
$healthOk = Test-CarroPortHealthy -Port $Port

if ($healthOk) {
  Write-Host "==> Engine already on http://127.0.0.1:$Port"
} else {
  Write-Host "==> Starting engine on http://127.0.0.1:$Port"
  $engine = Start-Process -FilePath $Py -ArgumentList @(
    "-m", "uvicorn", "carro_engine.main:app",
    "--host", "127.0.0.1", "--port", "$Port", "--no-access-log"
  ) -PassThru -NoNewWindow -WorkingDirectory $Root
  for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Milliseconds 300
    if (Test-CarroPortHealthy -Port $Port) { break }
  }
}

try {
  Set-Location (Join-Path $Root "advisor\ui")
  if (-not (Test-Path "node_modules")) { npm install }
  Write-Host "==> Advisor UI on http://127.0.0.1:1422 (proxies /api -> $($env:VITE_ENGINE_URL))"
  npm run dev
} finally {
  if ($engine -and -not $engine.HasExited) {
    Stop-Process -Id $engine.Id -Force -ErrorAction SilentlyContinue
  }
}
