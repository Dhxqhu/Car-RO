#!/usr/bin/env bash
# Install / refresh carro-server on a home-lab host (venv + optional systemd user unit).
set -euo pipefail

SOURCE="${BASH_SOURCE[0]:-$0}"
while [[ -L "$SOURCE" ]]; do
  SOURCE="$(readlink -f "$SOURCE")"
done
ROOT="$(cd "$(dirname "$SOURCE")/.." && pwd)"
SERVER_SRC="$ROOT/server"

PY="${PYTHON:-python3}"
INSTALL_DIR="${CARRO_SERVER_HOME:-$HOME/carro-server}"
DATA_DIR="${CARRO_DATA_DIR:-$HOME/carro-data}"
PORT="${CARRO_PORT:-8787}"

if ! command -v "$PY" >/dev/null 2>&1; then
  echo "error: python3 not found" >&2
  exit 1
fi

echo "==> Installing carro-server → $INSTALL_DIR"
mkdir -p "$INSTALL_DIR"
rsync -a --delete \
  --exclude '.venv' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  "$SERVER_SRC/" "$INSTALL_DIR/"

# Release identity for /health (opt-in updates — docs/UPDATING.md)
if [[ -f "$ROOT/VERSION" ]]; then
  cp -f "$ROOT/VERSION" "$INSTALL_DIR/VERSION"
fi

cd "$INSTALL_DIR"
if [[ ! -d .venv ]]; then
  "$PY" -m venv .venv
fi
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt

mkdir -p "$DATA_DIR"

ENV_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/carro-server.env"
mkdir -p "$(dirname "$ENV_FILE")"
if [[ ! -f "$ENV_FILE" ]]; then
  TOKEN="$(.venv/bin/python -c 'import secrets; print(secrets.token_urlsafe(24))')"
  cat >"$ENV_FILE" <<EOF
# carro-server environment (not for git)
CARRO_DATA_DIR=$DATA_DIR
CARRO_TOKEN=$TOKEN
# Optional multi-volume example:
# CARRO_VOLUMES=primary=$DATA_DIR,extra=/mnt/other/carro
EOF
  chmod 600 "$ENV_FILE"
  echo "==> Wrote $ENV_FILE (token generated)"
else
  # shellcheck disable=SC1090
  set -a
  # shellcheck disable=SC1090
  source "$ENV_FILE"
  set +a
  TOKEN="${CARRO_TOKEN:-}"
  echo "==> Keeping existing $ENV_FILE"
fi

UNIT_DIR="$HOME/.config/systemd/user"
mkdir -p "$UNIT_DIR"
UNIT="$UNIT_DIR/carro-server.service"
cat >"$UNIT" <<EOF
[Unit]
Description=Car-RO archive server
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=-$ENV_FILE
ExecStart=$INSTALL_DIR/.venv/bin/uvicorn carro_server.main:app --host 0.0.0.0 --port $PORT
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
EOF

echo "==> Wrote $UNIT"

if command -v systemctl >/dev/null 2>&1; then
  systemctl --user daemon-reload
  read -r -p "Enable and start carro-server now? [Y/n] " ans || true
  ans="${ans:-Y}"
  if [[ "$ans" =~ ^[Yy]$ ]]; then
    systemctl --user enable --now carro-server.service
    systemctl --user --no-pager --full status carro-server.service || true
    # linger so it survives logout on headless boxes
    if command -v loginctl >/dev/null 2>&1; then
      loginctl enable-linger "$USER" 2>/dev/null || true
    fi
  else
    echo "Start later with: systemctl --user enable --now carro-server"
  fi
else
  echo "No systemctl — run manually:"
  echo "  cd $INSTALL_DIR && set -a && source $ENV_FILE && set +a"
  echo "  PYTHONPATH=. .venv/bin/uvicorn carro_server.main:app --host 0.0.0.0 --port $PORT"
fi

# Best-effort hostname for the handoff block
HOST_HINT="$(hostname -s 2>/dev/null || hostname 2>/dev/null || echo YOUR_HOST)"
if command -v tailscale >/dev/null 2>&1; then
  TS_DNS="$(tailscale status --json 2>/dev/null | .venv/bin/python -c '
import json,sys
try:
  d=json.load(sys.stdin)
  print((d.get("Self") or {}).get("DNSName") or "")
except Exception:
  pass
' 2>/dev/null || true)"
  TS_DNS="${TS_DNS%.}"
  if [[ -n "$TS_DNS" ]]; then
    HOST_HINT="$TS_DNS"
  fi
fi
SERVER_URL="http://${HOST_HINT}:${PORT}"

echo
echo "############################################################"
echo "#  GIVE THIS TO EVERY BAY PC (same shop)                   #"
echo "############################################################"
echo "#"
echo "#  Server URL:"
echo "#    $SERVER_URL"
echo "#"
if [[ -n "${TOKEN:-}" ]]; then
  echo "#  Token:"
  echo "#    $TOKEN"
else
  echo "#  Token: (open $ENV_FILE and copy CARRO_TOKEN=...)"
fi
echo "#"
echo "#  On each bay PC after installing Car-RO:"
echo "#    ./scripts/join-server.sh"
echo "#  Or:"
echo "#    carro config set server_url $SERVER_URL"
if [[ -n "${TOKEN:-}" ]]; then
  echo "#    carro config set token $TOKEN"
else
  echo "#    carro config set token YOUR_TOKEN"
fi
echo "#    carro sync"
echo "#"
echo "#  Full guide: docs/SERVER_SETUP.md"
echo "############################################################"
echo
echo "Local health check: curl -s http://127.0.0.1:$PORT/health"
echo "Data dir: $DATA_DIR"
echo "Env file: $ENV_FILE"
echo "Add another photo drive later: ./scripts/add-server-volume.sh --help"
echo "  (docs: docs/SERVER_SETUP.md → Adding another drive)"
