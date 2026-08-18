#!/usr/bin/env bash
# Give the phone PWA a Tailscale HTTPS URL (required for iOS notifications).
#
# Does NOT take over https://…ts.net/ (port 443). That is often already
# another shop app (Open WebUI, etc.). Car-RO is published on :8443 instead.
#
# One-time on the shop server (needs sudo for tailscale serve):
#   sudo ./scripts/enable-pwa-https.sh
set -euo pipefail

PORT="${CARRO_PORT:-8787}"
HTTPS_PORT="${CARRO_HTTPS_PORT:-8443}"

if ! command -v tailscale >/dev/null 2>&1; then
  echo "error: tailscale not installed" >&2
  exit 1
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Tailscale Serve needs root once. Re-run:" >&2
  echo "  sudo $0" >&2
  exit 1
fi

tailscale serve --bg --https="$HTTPS_PORT" --yes "$PORT"

DNS="$(tailscale status --json 2>/dev/null | python3 -c 'import json,sys; print((json.load(sys.stdin).get("Self") or {}).get("DNSName") or "")' 2>/dev/null | sed 's/\.$//')"
if [[ -z "$DNS" ]]; then
  DNS="YOUR-SERVER.tailXXXX.ts.net"
fi

echo
echo "Car-RO HTTPS (tailnet only, not Funnel):"
echo "  https://${DNS}:${HTTPS_PORT}/"
echo
echo "On the phone: Tailscale on → open that URL in Safari → Add to Home Screen."
echo "Delete the old http:// icon first; iOS treats them as different apps."
echo
echo "Existing https://${DNS}/ (port 443) is left alone."
echo
tailscale serve status
