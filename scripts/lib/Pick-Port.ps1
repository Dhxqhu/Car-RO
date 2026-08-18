# Shared TCP port picker for Car-RO install / launch scripts (Windows).
# Usage:
#   . "$PSScriptRoot\lib\Pick-Port.ps1"
#   $Port = Get-CarroFreePort -Preferred 8787

function Test-CarroPortFree {
  param([Parameter(Mandatory = $true)][int]$Port)
  try {
    $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, $Port)
    $listener.Start()
    $listener.Stop()
    return $true
  } catch {
    return $false
  }
}

function Test-CarroPortHealthy {
  param([Parameter(Mandatory = $true)][int]$Port)
  try {
    $r = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec 1
    return ($r.StatusCode -ge 200 -and $r.StatusCode -lt 300)
  } catch {
    return $false
  }
}

function Wait-CarroPortHealthy {
  param(
    [Parameter(Mandatory = $true)][int]$Port,
    [double]$Seconds = 3
  )
  $deadline = [datetime]::UtcNow.AddSeconds($Seconds)
  while ([datetime]::UtcNow -lt $deadline) {
    if (Test-CarroPortHealthy -Port $Port) { return $true }
    if (Test-CarroPortFree -Port $Port) { return $false }
    Start-Sleep -Milliseconds 200
  }
  return (Test-CarroPortHealthy -Port $Port)
}

function Find-CarroHealthyPort {
  param(
    [int]$Start = 8788,
    [int]$End = 8808
  )
  for ($p = $Start; $p -le $End; $p++) {
    if (Test-CarroPortHealthy -Port $p) { return $p }
  }
  return $null
}

function Get-CarroFreePort {
  param(
    [int]$Preferred = 8787,
    [int]$MaxOffset = 20
  )
  if ($Preferred -lt 1 -or $Preferred -gt 65535) { $Preferred = 8787 }

  if (Test-CarroPortHealthy -Port $Preferred) { return $Preferred }
  if (-not (Test-CarroPortFree -Port $Preferred)) {
    if (Wait-CarroPortHealthy -Port $Preferred -Seconds 3) { return $Preferred }
  } else {
    return $Preferred
  }

  for ($offset = 1; $offset -le $MaxOffset; $offset++) {
    $p = $Preferred + $offset
    if ($p -gt 65535) { break }
    if (Test-CarroPortHealthy -Port $p) { return $p }
    if (-not (Test-CarroPortFree -Port $p)) {
      if (Wait-CarroPortHealthy -Port $p -Seconds 1) { return $p }
      continue
    }
    return $p
  }

  $listener = [System.Net.Sockets.TcpListener]::new([System.Net.IPAddress]::Loopback, 0)
  $listener.Start()
  $ephemeral = ([System.Net.IPEndPoint]$listener.LocalEndpoint).Port
  $listener.Stop()
  return $ephemeral
}

function Set-CarroEnvVar {
  param(
    [Parameter(Mandatory = $true)][string]$Path,
    [Parameter(Mandatory = $true)][string]$Key,
    [Parameter(Mandatory = $true)][string]$Value
  )
  $dir = Split-Path -Parent $Path
  if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
  if (-not (Test-Path $Path)) {
    Set-Content -Path $Path -Value "$Key=$Value" -Encoding utf8
    return
  }
  $lines = Get-Content -Path $Path
  $found = $false
  $out = foreach ($line in $lines) {
    if ($line -match "^\s*$([regex]::Escape($Key))=") {
      $found = $true
      "$Key=$Value"
    } else {
      $line
    }
  }
  if (-not $found) { $out = @($out) + @("$Key=$Value") }
  Set-Content -Path $Path -Value $out -Encoding utf8
}

function Resolve-CarroEnginePort {
  $configDir = if ($env:XDG_CONFIG_HOME) { $env:XDG_CONFIG_HOME } else { Join-Path $env:USERPROFILE ".config" }
  $envFile = Join-Path $configDir "carro\engine.env"

  if (-not $env:CARRO_ENGINE_PORT -and (Test-Path $envFile)) {
    Get-Content $envFile | ForEach-Object {
      if ($_ -match "^\s*CARRO_ENGINE_PORT=(.+)$") {
        $env:CARRO_ENGINE_PORT = $Matches[1].Trim()
      }
    }
  }

  $saved = $env:CARRO_ENGINE_PORT
  $chosen = Find-CarroHealthyPort -Start 8788 -End 8808
  if (-not $chosen -and $saved) {
    $savedPort = 0
    if ([int]::TryParse("$saved", [ref]$savedPort)) {
      if (Test-CarroPortHealthy -Port $savedPort) {
        $chosen = $savedPort
      } elseif (Wait-CarroPortHealthy -Port $savedPort -Seconds 3) {
        $chosen = $savedPort
      }
    }
  }
  if (-not $chosen) {
    if (Wait-CarroPortHealthy -Port 8788 -Seconds 3) { $chosen = 8788 }
  }
  if (-not $chosen) {
    $chosen = Get-CarroFreePort -Preferred 8788
  }

  if ($saved -and "$chosen" -ne "$saved") {
    Write-Host "==> Engine port $saved -> $chosen (joining existing or reclaiming default)"
  } elseif ($chosen -ne 8788) {
    Write-Host "==> Port 8788 busy - using engine port $chosen"
  }
  if ($chosen -gt 8808) {
    Write-Host "==> WARNING: engine on ephemeral port $chosen - tech + advisor must both use this port"
    Write-Host "    (set CARRO_ENGINE_PORT=$chosen or free ports 8788-8808 and relaunch)"
  }

  Set-CarroEnvVar -Path $envFile -Key "CARRO_ENGINE_PORT" -Value "$chosen"
  $env:CARRO_ENGINE_PORT = "$chosen"
  $env:VITE_ENGINE_URL = "http://127.0.0.1:$chosen"
  return $chosen
}
