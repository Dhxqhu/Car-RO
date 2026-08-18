#!/usr/bin/env bash
# Add another photo drive to a running carro-server (live, no code change).
#
# Usage (on the server, or any machine that can reach it):
#   ./scripts/add-server-volume.sh --name extra --path /mnt/extra/carro
#   ./scripts/add-server-volume.sh --name extra --path /mnt/extra/carro --make-default
#   ./scripts/add-server-volume.sh --list
#
# Env (optional):
#   CARRO_SERVER_URL   default http://127.0.0.1:8787
#   CARRO_TOKEN        or read from ~/.config/carro-server.env
set -euo pipefail

URL="${CARRO_SERVER_URL:-http://127.0.0.1:8787}"
TOKEN="${CARRO_TOKEN:-}"
NAME=""
PATH_DIR=""
MAKE_DEFAULT=0
LIST_ONLY=0
SET_DEFAULT=""

usage() {
  cat <<'EOF'
Add a photo storage volume to carro-server (live).

  ./scripts/add-server-volume.sh --name NAME --path /mount/point/carro [--make-default]
  ./scripts/add-server-volume.sh --list
  ./scripts/add-server-volume.sh --set-default NAME

Options:
  --name NAME          Short volume id (letters, digits, . _ -)
  --path DIR           Absolute path *on the server* (server creates it if missing)
  --make-default       New photos go to this volume (DB stays on CARRO_DATA_DIR)
  --set-default NAME   Only switch where new photos land
  --list               Show current volumes + free space
  --url URL            Server base URL (default: http://127.0.0.1:8787)
  --token TOKEN        Shop API token (or CARRO_TOKEN / carro-server.env)

Docs: docs/SERVER_SETUP.md  →  “Adding another drive (live server)”
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --name) NAME="${2:-}"; shift 2 ;;
    --path) PATH_DIR="${2:-}"; shift 2 ;;
    --make-default) MAKE_DEFAULT=1; shift ;;
    --set-default) SET_DEFAULT="${2:-}"; shift 2 ;;
    --list) LIST_ONLY=1; shift ;;
    --url) URL="${2:-}"; shift 2 ;;
    --token) TOKEN="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

URL="${URL%/}"

if [[ -z "$TOKEN" ]]; then
  ENV_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/carro-server.env"
  if [[ -f "$ENV_FILE" ]]; then
    # shellcheck disable=SC1090
    set -a
    # shellcheck disable=SC1090
    source "$ENV_FILE"
    set +a
    TOKEN="${CARRO_TOKEN:-}"
  fi
fi

if [[ -z "$TOKEN" ]]; then
  echo "error: set CARRO_TOKEN, pass --token, or run on the server with ~/.config/carro-server.env" >&2
  exit 1
fi

auth=(-H "Authorization: Bearer $TOKEN" -H "Accept: application/json")

if [[ "$LIST_ONLY" -eq 1 ]]; then
  curl -fsS "${auth[@]}" "$URL/volumes" | python3 -m json.tool
  exit 0
fi

if [[ -n "$SET_DEFAULT" ]]; then
  curl -fsS "${auth[@]}" -X PUT "$URL/volumes/${SET_DEFAULT}/default" | python3 -m json.tool
  echo
  echo "New photo uploads will use volume '$SET_DEFAULT'. Existing photos stay where they are."
  exit 0
fi

if [[ -z "$NAME" || -z "$PATH_DIR" ]]; then
  echo "error: --name and --path are required (or use --list / --set-default)" >&2
  usage
  exit 2
fi

# When talking to localhost, pre-create the mount path so mount mistakes fail early.
case "$URL" in
  http://127.0.0.1:*|http://localhost:*|http://[::1]:*)
    if [[ ! -d "$PATH_DIR" ]]; then
      echo "==> Creating $PATH_DIR on this host"
      mkdir -p "$PATH_DIR"
    fi
    ;;
esac

BODY=$(python3 -c 'import json,sys; print(json.dumps({"name":sys.argv[1],"path":sys.argv[2],"make_default":sys.argv[3]=="1"}))' \
  "$NAME" "$PATH_DIR" "$MAKE_DEFAULT")

echo "==> POST $URL/volumes"
echo "    name=$NAME path=$PATH_DIR make_default=$MAKE_DEFAULT"
curl -fsS "${auth[@]}" -H "Content-Type: application/json" \
  -d "$BODY" "$URL/volumes" | python3 -m json.tool

echo
if [[ "$MAKE_DEFAULT" -eq 1 ]]; then
  echo "Done. New photos will land on volume '$NAME'."
else
  echo "Done. Volume '$NAME' is registered. To send new photos there:"
  echo "  $0 --set-default $NAME"
fi
echo "Old photos stay on their original volume; downloads search all volumes."
