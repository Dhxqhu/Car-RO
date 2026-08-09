#!/usr/bin/env bash
# Launch Tauri GUI with local Python engine (dev).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export CARRO_ROOT="$ROOT"
export PYTHONPATH="$ROOT/cli:$ROOT/server:$ROOT/engine${PYTHONPATH:+:$PYTHONPATH}"
export PATH="${HOME}/.cargo/bin:${PATH}"

# Start engine in background
PY="${ROOT}/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "error: run ./scripts/install.sh first" >&2
  exit 1
fi
"$PY" -m uvicorn carro_engine.main:app --host 127.0.0.1 --port 8788 &
ENGINE_PID=$!
trap 'kill $ENGINE_PID 2>/dev/null || true' EXIT
sleep 0.5

cd "$ROOT/gui"
if [[ ! -d node_modules ]]; then npm install; fi
if [[ ! -d ui/node_modules ]]; then npm --prefix ui install; fi
npm run tauri:dev
