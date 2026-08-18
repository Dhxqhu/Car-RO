#!/usr/bin/env bash
# Start local engine + Vite UI for GUI development.
# Usage:
#   ./scripts/run-gui-dev.sh           # full app (login → Orders or Open Scanner)
#   ./scripts/run-gui-dev.sh --scanner # scanner-only (skip login / no Orders)
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# shellcheck disable=SC1091
source "$ROOT/scripts/lib/pick-port.sh"
# shellcheck disable=SC1091
source "$ROOT/scripts/lib/engine-port.sh"

SCANNER_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --scanner|-s) SCANNER_ONLY=1 ;;
  esac
done

export PYTHONPATH="$ROOT/cli:$ROOT/server:$ROOT/engine${PYTHONPATH:+:$PYTHONPATH}"
if [[ -d "$(dirname "$ROOT")/obdscan" ]]; then
  export OBDSCAN_ROOT="${OBDSCAN_ROOT:-$(dirname "$ROOT")/obdscan}"
fi

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
fi

cd "$ROOT/gui/ui"
if [[ ! -d node_modules ]]; then
  npm install
fi

if [[ "$SCANNER_ONLY" -eq 1 ]]; then
  export VITE_CARRO_MODE=scanner
  echo "==> UI (scanner-only) on http://127.0.0.1:1420/?mode=scanner"
else
  unset VITE_CARRO_MODE || true
  echo "==> UI on http://127.0.0.1:1420 (proxies /api → $VITE_ENGINE_URL)"
fi
npm run dev
