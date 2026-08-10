# Dev launcher for Car-RO Advisor desk UI (starts local engine if needed).
# Usage: .\scripts\run-advisor-ui.ps1
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
$engine = $null
$healthOk = $false
try {
  $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec 1
  if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300) { $healthOk = $true }
} catch { $healthOk = $false }

if ($healthOk) {
  Write-Host "==> Engine already on http://127.0.0.1:$Port"
} else {
  Write-Host "==> Starting engine on http://127.0.0.1:$Port"
  $engine = Start-Process -FilePath $Py -ArgumentList @(
    "-m", "uvicorn", "carro_engine.main:app",
    "--host", "127.0.0.1", "--port", $Port
  ) -PassThru -NoNewWindow -WorkingDirectory $Root
  for ($i = 0; $i -lt 20; $i++) {
    Start-Sleep -Milliseconds 300
    try {
      $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec 1
      if ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300) { break }
    } catch { }
  }
}

try {
  Set-Location (Join-Path $Root "advisor\ui")
  if (-not (Test-Path "node_modules")) { npm install }
  Write-Host "==> Advisor UI on http://127.0.0.1:1422 (proxies /api → engine)"
  npm run dev
} finally {
  if ($engine -and -not $engine.HasExited) {
    Stop-Process -Id $engine.Id -Force -ErrorAction SilentlyContinue
  }
}
