#!/usr/bin/env bash
# Dev launcher for Car-RO Advisor desk UI (starts local engine if needed).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# shellcheck disable=SC1091
source "$ROOT/scripts/lib/pick-port.sh"
# shellcheck disable=SC1091
source "$ROOT/scripts/lib/engine-port.sh"

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
  echo "==> Starting engine on http://127.0.0.1:$PORT"
  # --no-access-log: UI polls /events /messages every few seconds; keep terminal readable.
  "$PY" -m uvicorn carro_engine.main:app --host 127.0.0.1 --port "$PORT" --no-access-log &
  ENGINE_PID=$!
  trap 'kill $ENGINE_PID 2>/dev/null || true' EXIT
  # Wait briefly for listen
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    if curl -sf -m 1 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
      break
    fi
    sleep 0.3
  done
fi

cd "$ROOT/advisor/ui"
if [[ ! -d node_modules ]]; then
  npm install
fi
echo "==> Advisor UI on http://127.0.0.1:1422 (proxies /api → $VITE_ENGINE_URL)"
exec npm run dev
