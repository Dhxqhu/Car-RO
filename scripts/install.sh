#!/usr/bin/env bash
# Install Car-RO CLI on this workstation (venv + carro on PATH + config stub).
set -euo pipefail

SOURCE="${BASH_SOURCE[0]:-$0}"
while [[ -L "$SOURCE" ]]; do
  SOURCE="$(readlink -f "$SOURCE")"
done
ROOT="$(cd "$(dirname "$SOURCE")/.." && pwd)"
cd "$ROOT"

PY="${PYTHON:-python3}"
if ! command -v "$PY" >/dev/null 2>&1; then
  echo "error: python3 not found" >&2
  exit 1
fi

echo "==> Car-RO install from $ROOT"

if [[ ! -d .venv ]]; then
  echo "==> Creating .venv"
  "$PY" -m venv .venv
fi

echo "==> Installing Python dependencies"
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt

BIN_DIR="${CARRO_BIN_DIR:-$HOME/.local/bin}"
mkdir -p "$BIN_DIR"
ln -sfn "$ROOT/scripts/carro" "$BIN_DIR/carro"
echo "==> Linked $BIN_DIR/carro → scripts/carro"

CONFIG_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/carro"
mkdir -p "$CONFIG_DIR"
if [[ ! -f "$CONFIG_DIR/config.toml" ]]; then
  cp "$ROOT/config.example.toml" "$CONFIG_DIR/config.toml"
  echo "==> Wrote $CONFIG_DIR/config.toml (edit shop name / server as needed)"
else
  echo "==> Keeping existing $CONFIG_DIR/config.toml"
fi

DOC_ROOT="${CARRO_DOCS:-$HOME/Documents/Car-RO}"
mkdir -p "$DOC_ROOT/photos" "$DOC_ROOT/inbox" "$DOC_ROOT/branding"

# Ensure dirs via app as well (pdf cache, etc.)
export PYTHONPATH="$ROOT/cli:$ROOT/server${PYTHONPATH:+:$PYTHONPATH}"
.venv/bin/python -m carro config init >/dev/null 2>&1 || true

case ":$PATH:" in
  *":$BIN_DIR:"*) ;;
  *)
    echo
    echo "note: $BIN_DIR is not on your PATH."
    echo "  Add this to your shell rc, then reopen the terminal:"
    echo "    export PATH=\"$BIN_DIR:\$PATH\""
    ;;
esac

echo
echo "Done. Try:"
echo "  carro"
echo "  carro config"
echo
echo "Optional home-lab server: ./scripts/install-server.sh"
echo "Docs: README.md"
