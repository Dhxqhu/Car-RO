#!/usr/bin/env bash
# Start local engine + Vite UI for GUI development.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export PYTHONPATH="$ROOT/cli:$ROOT/server:$ROOT/engine${PYTHONPATH:+:$PYTHONPATH}"
PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "error: run ./scripts/install.sh first" >&2
  exit 1
fi

PORT="${CARRO_ENGINE_PORT:-8788}"
echo "==> Engine on http://127.0.0.1:$PORT"
"$PY" -m uvicorn carro_engine.main:app --host 127.0.0.1 --port "$PORT" &
ENGINE_PID=$!
trap 'kill $ENGINE_PID 2>/dev/null || true' EXIT

cd "$ROOT/gui/ui"
if [[ ! -d node_modules ]]; then
  npm install
fi
echo "==> UI on http://127.0.0.1:1420 (proxies /api → engine)"
npm run dev
