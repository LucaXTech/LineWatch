#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

echo "UplinkWitness configuration"
echo
echo "UplinkWitness can run with any ordinary Linux Internet connection."
echo "FRITZ!Box credentials are only needed for enhanced TR-064 diagnostics"
echo "such as router reboot and WAN/PPPoE session reset detection."
echo

read -r -p "Enable FRITZ!Box enhanced diagnostics? [y/N]: " FRITZ_ENABLE
FRITZ_ENABLE="${FRITZ_ENABLE:-N}"

MODE="generic"
FRITZ_USER_INPUT=""
FRITZ_PASSWORD_INPUT=""
FRITZ_HOST_INPUT=""

case "$FRITZ_ENABLE" in
  y|Y|yes|YES|Yes)
    MODE="fritz"
    read -r -p "FRITZ!Box username: " FRITZ_USER_INPUT
    if [ -z "$FRITZ_USER_INPUT" ]; then
      echo "Username cannot be empty in FRITZ mode."
      exit 1
    fi

    read -r -s -p "FRITZ!Box password: " FRITZ_PASSWORD_INPUT
    echo
    if [ -z "$FRITZ_PASSWORD_INPUT" ]; then
      echo "Password cannot be empty in FRITZ mode."
      exit 1
    fi

    read -r -p "FRITZ!Box IPv4 address [default gateway]: " FRITZ_HOST_INPUT
    ;;
esac

python3 - "$MODE" "$FRITZ_USER_INPUT" "$FRITZ_PASSWORD_INPUT" "$FRITZ_HOST_INPUT" <<'PY'
import shlex
import sys
from pathlib import Path

mode, user, password, host = sys.argv[1:5]
path = Path(".env")
defaults = {
    "LINEWATCH_ROUTER_MODE": mode,
    "FRITZ_USER": user,
    "FRITZ_PASSWORD": password,
    "FRITZ_HOST": host,
    "LINEWATCH_INTERFACE": "",
    "LINEWATCH_GATEWAY_PROBE": "auto",
    "LINEWATCH_POLL_SECONDS": "2",
    "LINEWATCH_HEALTHY_PERSIST_SECONDS": "30",
    "LINEWATCH_FRITZ_POLL_SECONDS": "10",
    "LINEWATCH_PUBLIC_IP_SECONDS": "300",
    "LINEWATCH_RING_SECONDS": "120",
    "LINEWATCH_PING_TARGETS": "1.1.1.1,8.8.8.8",
    "LINEWATCH_DNS_NAME": "www.cloudflare.com",
    "LINEWATCH_HTTP_URL": "https://connectivitycheck.gstatic.com/generate_204",
    "LINEWATCH_PUBLIC_IP_URL": "https://api.ipify.org",
}
with path.open("w", encoding="utf-8") as f:
    for key, value in defaults.items():
        f.write(f"{key}={shlex.quote(value)}\n")
PY

chmod 600 .env
echo
echo "Configuration saved to $APP_DIR/.env"
if [ "$MODE" = "fritz" ]; then
  echo "Mode: FRITZ!Box enhanced diagnostics"
else
  echo "Mode: generic Linux Internet monitoring"
fi
