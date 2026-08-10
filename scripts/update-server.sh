#!/usr/bin/env bash
# Opt-in refresh of carro-server on a live host.
# Preserves ~/.config/carro-server.env (token) and data dir. Never regenerates the shop token.
#
# Typical use after git pull / copying a new release into the Car-RO checkout:
#   ./scripts/update-server.sh
set -euo pipefail

SOURCE="${BASH_SOURCE[0]:-$0}"
while [[ -L "$SOURCE" ]]; do
  SOURCE="$(readlink -f "$SOURCE")"
done
ROOT="$(cd "$(dirname "$SOURCE")/.." && pwd)"
SERVER_SRC="$ROOT/server"

PY="${PYTHON:-python3}"
INSTALL_DIR="${CARRO_SERVER_HOME:-$HOME/carro-server}"
ENV_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/carro-server.env"
PORT="${CARRO_PORT:-8787}"

read_ver() {
  local f="$1"
  if [[ -f "$f" ]]; then
    head -n 1 "$f" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
  else
    echo "unknown"
  fi
}

BEFORE="$(read_ver "$INSTALL_DIR/VERSION")"
AFTER="$(read_ver "$ROOT/VERSION")"

if [[ ! -d "$INSTALL_DIR" ]]; then
  echo "error: $INSTALL_DIR not found — run ./scripts/install-server.sh first" >&2
  exit 1
fi
if [[ ! -f "$ENV_FILE" ]]; then
  echo "error: missing $ENV_FILE — refusing to update (would risk wiping shop token)" >&2
  exit 1
fi

# shellcheck disable=SC1090
set -a
# shellcheck disable=SC1090
source "$ENV_FILE"
set +a
DATA_DIR="${CARRO_DATA_DIR:-$HOME/carro-data}"
if [[ ! -d "$DATA_DIR" ]]; then
  echo "error: data dir $DATA_DIR missing — refusing to update" >&2
  exit 1
fi

echo "==> Updating carro-server"
echo "    install: $INSTALL_DIR"
echo "    version: $BEFORE → $AFTER"
echo "    data:    $DATA_DIR (untouched)"
echo "    env:     $ENV_FILE (token preserved)"

rsync -a --delete \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  "$SERVER_SRC/" "$INSTALL_DIR/"

# Release identity for /health on the installed tree
if [[ -f "$ROOT/VERSION" ]]; then
  cp -f "$ROOT/VERSION" "$INSTALL_DIR/VERSION"
fi

cd "$INSTALL_DIR"
if [[ ! -d .venv ]]; then
  "$PY" -m venv .venv
fi
.venv/bin/pip install -q -U pip
.venv/bin/pip install -q -r requirements.txt

if command -v systemctl >/dev/null 2>&1; then
  systemctl --user daemon-reload
  systemctl --user restart carro-server.service
  sleep 1
  systemctl --user --no-pager --full status carro-server.service | head -15 || true
else
  echo "note: no systemctl — restart uvicorn manually"
fi

echo
echo "Health:"
curl -sS -m 5 "http://127.0.0.1:${PORT}/health" || echo "(health check failed — check service logs)"
echo
echo "Done. Shop clients do not need to update unless you want new features on those PCs."
echo "See docs/UPDATING.md"
