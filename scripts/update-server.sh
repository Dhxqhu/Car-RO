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

# shellcheck disable=SC1091
source "$ROOT/scripts/lib/pick-port.sh"

PY="${PYTHON:-python3}"
INSTALL_DIR="${CARRO_SERVER_HOME:-$HOME/carro-server}"
ENV_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/carro-server.env"
CALLER_PORT="${CARRO_PORT:-}"

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

if [[ -n "$CALLER_PORT" ]]; then
  PREFERRED_PORT="$CALLER_PORT"
elif [[ -n "${CARRO_PORT:-}" ]]; then
  PREFERRED_PORT="$CARRO_PORT"
else
  PREFERRED_PORT=8787
fi

PORT_CHANGED=0
OLD_PORT="$PREFERRED_PORT"
# Keep stored port if healthy or free; otherwise re-pick (something else took it).
if carro_port_healthy "$PREFERRED_PORT" || _carro_port_free "$PREFERRED_PORT"; then
  PORT="$PREFERRED_PORT"
else
  PORT="$(pick_port "$PREFERRED_PORT")"
  if [[ "$PORT" != "$PREFERRED_PORT" ]]; then
    PORT_CHANGED=1
    echo "==> Stored port $PREFERRED_PORT is busy — switching to $PORT"
    echo "    Update each bay: carro config set server_url http://YOUR_HOST:$PORT"
  fi
fi
upsert_env_var "$ENV_FILE" "CARRO_PORT" "$PORT"
export CARRO_PORT="$PORT"

echo "==> Updating carro-server"
echo "    install: $INSTALL_DIR"
echo "    version: $BEFORE → $AFTER"
echo "    data:    $DATA_DIR (untouched)"
echo "    env:     $ENV_FILE (token preserved)"
echo "    port:    $PORT"

if command -v npm >/dev/null 2>&1 && [[ -f "$ROOT/mobile/package.json" ]]; then
  echo "==> Building phone PWA"
  "$ROOT/scripts/build-pwa.sh" || echo "warning: phone PWA build failed (server still updates)"
fi

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

UNIT_DIR="$HOME/.config/systemd/user"
UNIT="$UNIT_DIR/carro-server.service"
if [[ -d "$UNIT_DIR" ]]; then
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
fi

if command -v systemctl >/dev/null 2>&1; then
  systemctl --user daemon-reload
  systemctl --user restart carro-server.service
  sleep 1
  systemctl --user --no-pager --full status carro-server.service | head -15 || true
else
  echo "note: no systemctl — restart uvicorn manually on port $PORT"
fi

echo
echo "Health:"
curl -sS -m 5 "http://127.0.0.1:${PORT}/health" || echo "(health check failed — check service logs)"
echo
if [[ "$PORT_CHANGED" -eq 1 ]]; then
  echo "Port changed from $OLD_PORT to $PORT — re-join bays with the new server URL."
fi
echo "Done. Shop clients do not need to update unless you want new features on those PCs."
echo "See docs/UPDATING.md"
