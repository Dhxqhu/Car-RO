#!/usr/bin/env bash
# Resolve local engine port (default 8788), with fallback + persistence.
# Usage (from a launcher):
#   source "$ROOT/scripts/lib/pick-port.sh"
#   source "$ROOT/scripts/lib/engine-port.sh"
#   resolve_engine_port   # sets ENGINE_PORT, exports CARRO_ENGINE_PORT + VITE_ENGINE_URL
#
# Dual-app same machine: always prefer an already-healthy engine in 8788–8808
# so tech + advisor UIs share one process (sessions, events, messaging).

_carro_engine_env_file() {
  echo "${XDG_CONFIG_HOME:-$HOME/.config}/carro/engine.env"
}

resolve_engine_port() {
  local env_file preferred chosen saved
  env_file="$(_carro_engine_env_file)"

  if [[ -z "${CARRO_ENGINE_PORT:-}" && -f "$env_file" ]]; then
    # shellcheck disable=SC1090
    set -a
    # shellcheck disable=SC1090
    source "$env_file"
    set +a
  fi

  saved="${CARRO_ENGINE_PORT:-}"
  # Canonical sticky default — do not keep chasing a drifted/ephemeral port
  # when nothing is running (avoids tech on :8788 vs advisor on :52100).
  preferred=8788
  if [[ -n "${saved}" && "$saved" =~ ^[0-9]+$ ]]; then
    preferred="$saved"
  fi

  chosen=""
  # 1) Any live engine in the sticky band wins (second launcher joins the first).
  chosen="$(carro_find_healthy_port 8788 8808 || true)"
  # 2) Saved port may be outside the band (older ephemeral) — reuse if healthy.
  if [[ -z "$chosen" && -n "$saved" && "$saved" =~ ^[0-9]+$ ]]; then
    if carro_port_healthy "$saved"; then
      chosen="$saved"
    elif carro_wait_healthy "$saved" 3; then
      chosen="$saved"
    fi
  fi
  # 3) Startup race: peer launcher bound 8788 but /health not ready yet.
  if [[ -z "$chosen" ]]; then
    if carro_wait_healthy 8788 3; then
      chosen=8788
    fi
  fi
  # 4) Allocate from the sticky default, not a drifted preferred.
  if [[ -z "$chosen" ]]; then
    chosen="$(pick_port 8788)"
  fi

  if [[ -n "$saved" && "$chosen" != "$saved" ]]; then
    echo "==> Engine port $saved → $chosen (joining existing or reclaiming default)" >&2
  elif [[ "$chosen" != "8788" ]]; then
    echo "==> Port 8788 busy — using engine port $chosen" >&2
  fi
  if (( chosen > 8808 )); then
    echo "==> WARNING: engine on ephemeral port $chosen — tech + advisor must both use this port" >&2
    echo "    (set CARRO_ENGINE_PORT=$chosen or free ports 8788–8808 and relaunch)" >&2
  fi

  mkdir -p "$(dirname "$env_file")"
  upsert_env_var "$env_file" "CARRO_ENGINE_PORT" "$chosen"

  ENGINE_PORT="$chosen"
  export CARRO_ENGINE_PORT="$chosen"
  export VITE_ENGINE_URL="http://127.0.0.1:${chosen}"
}
