#!/usr/bin/env bash
# Build the phone PWA into server/pwa (served by carro-server).
set -euo pipefail

SOURCE="${BASH_SOURCE[0]:-$0}"
while [[ -L "$SOURCE" ]]; do
  SOURCE="$(readlink -f "$SOURCE")"
done
ROOT="$(cd "$(dirname "$SOURCE")/.." && pwd)"
MOBILE="$ROOT/mobile"
DEST="$ROOT/server/pwa"

if ! command -v npm >/dev/null 2>&1; then
  echo "error: npm not found — install Node.js to build the phone app" >&2
  exit 1
fi

PY="${PYTHON:-python3}"
if [[ -x "$ROOT/.venv/bin/python" ]]; then
  PY="$ROOT/.venv/bin/python"
fi
"$PY" "$ROOT/scripts/generate-pwa-icons.py"

cd "$MOBILE"
if [[ ! -d node_modules ]]; then
  npm install
fi
npm run build

mkdir -p "$DEST"
rsync -a --delete "$MOBILE/dist/" "$DEST/"
echo "==> Phone PWA → $DEST"
echo "    After install/update, open http://SHOP-SERVER:8787/ on a phone."
