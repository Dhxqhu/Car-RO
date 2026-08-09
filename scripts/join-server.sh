#!/usr/bin/env bash
# Point this bay PC at an existing carro-server (URL + token).
set -euo pipefail

SOURCE="${BASH_SOURCE[0]:-$0}"
while [[ -L "$SOURCE" ]]; do
  SOURCE="$(readlink -f "$SOURCE")"
done
ROOT="$(cd "$(dirname "$SOURCE")/.." && pwd)"

export PYTHONPATH="$ROOT/cli:$ROOT/server${PYTHONPATH:+:$PYTHONPATH}"
PY="$ROOT/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "error: run ./scripts/install.sh first (need .venv)" >&2
  exit 1
fi

echo "=============================================="
echo "  Join an existing Car-RO server (bay PC)"
echo "=============================================="
echo
echo "Use the URL + token from the server install output"
echo "(or on the server: grep CARRO_TOKEN ~/.config/carro-server.env)."
echo
echo "This is the shop API token — the same value on every bay PC."
echo "Do not generate a new token on this laptop unless you also"
echo "changed CARRO_TOKEN on the server (see docs/SERVER_SETUP.md)."
echo

read -r -p "Server URL (e.g. http://homebaseserver:8787): " URL
URL="${URL// /}"
URL="${URL%/}"
if [[ -z "$URL" ]]; then
  echo "error: URL required" >&2
  exit 1
fi

read -r -p "API token: " TOKEN
TOKEN="${TOKEN// /}"
if [[ -z "$TOKEN" ]]; then
  echo "error: token required" >&2
  exit 1
fi

"$PY" -m carro config set server_url "$URL"
"$PY" -m carro config set token "$TOKEN"

echo
echo "==> Checking server…"
if "$PY" - <<PY
from carro.storage.remote import RemoteClient
r = RemoteClient()
h = r.health()
print("OK", h)
PY
then
  echo
  echo "Joined. Next:"
  echo "  carro sync"
  echo "  carro          # login / use menu"
else
  echo
  echo "Saved URL + token, but health check failed."
  echo "Fix network / Tailscale / token, then: carro sync"
  exit 1
fi
