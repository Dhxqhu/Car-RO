#!/usr/bin/env bash
# Launch Tauri GUI with local Python engine (dev).
# Usage:
#   ./scripts/run-gui-tauri.sh
#   ./scripts/run-gui-tauri.sh --scanner
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export CARRO_ROOT="$ROOT"
export PYTHONPATH="$ROOT/cli:$ROOT/server:$ROOT/engine${PYTHONPATH:+:$PYTHONPATH}"
export PATH="${HOME}/.cargo/bin:${PATH}"

# shellcheck disable=SC1091
source "$ROOT/scripts/lib/pick-port.sh"
# shellcheck disable=SC1091
source "$ROOT/scripts/lib/engine-port.sh"

if [[ -d "$(dirname "$ROOT")/obdscan" ]]; then
  export OBDSCAN_ROOT="${OBDSCAN_ROOT:-$(dirname "$ROOT")/obdscan}"
fi

for arg in "$@"; do
  case "$arg" in
    --scanner|-s) export VITE_CARRO_MODE=scanner ;;
  esac
done

# Start engine in background
PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "error: run ./scripts/install.sh first" >&2
  exit 1
fi

resolve_engine_port
PORT="$ENGINE_PORT"
ENGINE_PID=""
if curl -sf -m 1 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
  echo "==> Engine already on http://127.0.0.1:$PORT"
else
  echo "==> Engine on http://127.0.0.1:$PORT"
  # --no-access-log: UI polls /events /messages every few seconds; keep terminal readable.
  "$PY" -m uvicorn carro_engine.main:app --host 127.0.0.1 --port "$PORT" --no-access-log &
  ENGINE_PID=$!
  trap 'kill $ENGINE_PID 2>/dev/null || true' EXIT
  sleep 0.5
fi

cd "$ROOT/gui"
if [[ ! -d node_modules ]]; then npm install; fi
if [[ ! -d ui/node_modules ]]; then npm --prefix ui install; fi
npm run tauri:dev
