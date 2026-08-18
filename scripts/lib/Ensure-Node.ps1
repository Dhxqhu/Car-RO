# Put Node.js on PATH for this process if a fresh install has not
# refreshed Explorer yet (double-clicked .bat still has the old PATH).

function Repair-CarroNodePath {
  if (Get-Command node -ErrorAction SilentlyContinue) { return }

  $dirs = @(
    (Join-Path $env:ProgramFiles "nodejs"),
    (Join-Path ${env:ProgramFiles(x86)} "nodejs"),
    (Join-Path $env:LOCALAPPDATA "nodejs"),
    (Join-Path $env:LOCALAPPDATA "Programs\nodejs"),
    (Join-Path $env:APPDATA "npm")
  )
  foreach ($d in $dirs) {
    if ($d -and (Test-Path $d)) {
      $env:PATH = "$d;$env:PATH"
    }
  }

  if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Error @"
Node.js was not found on PATH.
Install Node 20+ from https://nodejs.org (LTS), then run this launcher again.
You do not need to reboot; a new terminal is enough after install.
"@
  }
}

Repair-CarroNodePath
