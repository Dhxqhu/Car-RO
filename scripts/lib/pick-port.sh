#!/usr/bin/env bash
# Shared TCP port picker for Car-RO install / launch scripts.
# Usage:
#   source "$ROOT/scripts/lib/pick-port.sh"
#   PORT="$(pick_port 8787)"   # prints free port on stdout
#
# Prefers PREFERRED, then PREFERRED+1 … PREFERRED+20, then an OS ephemeral port.
# When PREFERRED is bound but /health is not ready yet (startup race), waits briefly
# so a second launcher joins the same process instead of spawning another engine.

_carro_port_free() {
  local port="$1"
  local py="${PYTHON:-python3}"
  "$py" - "$port" <<'PY' 2>/dev/null
import socket, sys
port = int(sys.argv[1])
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.bind(("127.0.0.1", port))
except OSError:
    sys.exit(1)
finally:
    s.close()
sys.exit(0)
PY
}

_carro_ephemeral_port() {
  local py="${PYTHON:-python3}"
  "$py" - <<'PY'
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
s.bind(("127.0.0.1", 0))
print(s.getsockname()[1])
s.close()
PY
}

# True if something already answers Car-RO /health on this port.
carro_port_healthy() {
  local port="$1"
  curl -sf -m 1 "http://127.0.0.1:${port}/health" >/dev/null 2>&1
}

# Wait until /health answers, or timeout (seconds). Returns 0 if healthy.
carro_wait_healthy() {
  local port="$1"
  local seconds="${2:-3}"
  local py="${PYTHON:-python3}"
  local end
  end="$("$py" -c "import time; print(time.time() + float('${seconds}'))")"
  while "$py" -c "import time,sys; sys.exit(0 if time.time() < float('${end}') else 1)"; do
    if carro_port_healthy "$port"; then
      return 0
    fi
    # Only wait while something is bound (startup), otherwise bail early.
    if _carro_port_free "$port"; then
      return 1
    fi
    sleep 0.2
  done
  carro_port_healthy "$port"
}

# First healthy Car-RO engine in [start, end], or empty.
carro_find_healthy_port() {
  local start="${1:-8788}"
  local end="${2:-8808}"
  local p
  for ((p = start; p <= end; p++)); do
    if carro_port_healthy "$p"; then
      echo "$p"
      return 0
    fi
  done
  return 1
}

# Pick a free listen port. If PREFERRED already serves /health, keep it.
# If PREFERRED is bound but not healthy yet, wait briefly before falling through.
pick_port() {
  local preferred="${1:-8787}"
  local max_offset="${2:-20}"
  local p offset

  if ! [[ "$preferred" =~ ^[0-9]+$ ]] || (( preferred < 1 || preferred > 65535 )); then
    preferred=8787
  fi

  if carro_port_healthy "$preferred"; then
    echo "$preferred"
    return 0
  fi
  if ! _carro_port_free "$preferred"; then
    if carro_wait_healthy "$preferred" 3; then
      echo "$preferred"
      return 0
    fi
  else
    echo "$preferred"
    return 0
  fi

  for ((offset = 1; offset <= max_offset; offset++)); do
    p=$((preferred + offset))
    if (( p > 65535 )); then
      break
    fi
    if carro_port_healthy "$p"; then
      echo "$p"
      return 0
    fi
    if ! _carro_port_free "$p"; then
      if carro_wait_healthy "$p" 1; then
        echo "$p"
        return 0
      fi
      continue
    fi
    echo "$p"
    return 0
  done

  _carro_ephemeral_port
}

# Upsert KEY=VALUE in an env file (creates file if missing).
upsert_env_var() {
  local file="$1"
  local key="$2"
  local value="$3"
  mkdir -p "$(dirname "$file")"
  if [[ ! -f "$file" ]]; then
    printf '%s=%s\n' "$key" "$value" >"$file"
    return 0
  fi
  if grep -qE "^[[:space:]]*${key}=" "$file"; then
    local tmp
    tmp="$(mktemp)"
    # shellcheck disable=SC2002
    sed -E "s|^[[:space:]]*${key}=.*|${key}=${value}|" "$file" >"$tmp"
    mv "$tmp" "$file"
  else
    printf '\n%s=%s\n' "$key" "$value" >>"$file"
  fi
}
