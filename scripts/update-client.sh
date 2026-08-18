#!/usr/bin/env bash
# Opt-in refresh of this bay / advisor PC (CLI + Python deps; optional UI node_modules).
# Keeps ~/.config/carro/config.toml. Does not touch shop server data.
#
# After git pull / new release in this checkout:
#   ./scripts/update-client.sh
set -euo pipefail

SOURCE="${BASH_SOURCE[0]:-$0}"
while [[ -L "$SOURCE" ]]; do
  SOURCE="$(readlink -f "$SOURCE")"
done
ROOT="$(cd "$(dirname "$SOURCE")/.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-python3}"
CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/carro"

read_ver() {
  local f="$1"
  if [[ -f "$f" ]]; then
    head -n 1 "$f" | tr -d '\r' | sed 's/^[[:space:]]*//;s/[[:space:]]*$//'
  else
    echo "unknown"
  fi
}

BEFORE="$(read_ver "$ROOT/VERSION")"
echo "==> Updating Car-RO client at $ROOT"
echo "    VERSION: $BEFORE (source tree)"

if [[ -f "$CONFIG_DIR/config.toml" ]]; then
  echo "    config: $CONFIG_DIR/config.toml (kept)"
else
  echo "    note: no config.toml yet — run ./scripts/install.sh if this is a new PC"
fi

if [[ ! -d .venv ]]; then
  echo "==> Creating .venv"
  "$PY" -m venv .venv
fi

.venv/bin/pip install -q -U pip
.venv/bin/pip install -q -r requirements.txt

BIN_DIR="${CARRO_BIN_DIR:-$HOME/.local/bin}"
mkdir -p "$BIN_DIR"
ln -sfn "$ROOT/scripts/carro" "$BIN_DIR/carro"
ln -sfn "$ROOT/scripts/carroadviser" "$BIN_DIR/carroadviser"

# Refresh UI deps when present (dev launchers)
if [[ -d "$ROOT/gui/ui" ]]; then
  if [[ -d "$ROOT/gui/ui/node_modules" ]] || [[ "${CARRO_UPDATE_UI:-}" == "1" ]]; then
    echo "==> npm install (tech GUI)"
    (cd "$ROOT/gui/ui" && npm install)
  fi
fi
if [[ -d "$ROOT/advisor/ui" ]]; then
  if [[ -d "$ROOT/advisor/ui/node_modules" ]] || [[ "${CARRO_UPDATE_UI:-}" == "1" ]]; then
    echo "==> npm install (advisor GUI)"
    (cd "$ROOT/advisor/ui" && npm install)
  fi
fi

AFTER="$(read_ver "$ROOT/VERSION")"
echo
echo "Done. Client VERSION: $AFTER"
echo "Restart the local engine + GUI if they were running:"
echo "  ./scripts/run-gui-dev.sh          # tech"
echo "  ./scripts/run-advisor-ui.sh       # advisor"
echo
echo "You only need this when you want newer features on this PC."
echo "Update carro-server first if this build requires a newer shop API (docs/UPDATING.md)."
