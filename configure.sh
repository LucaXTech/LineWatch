#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$APP_DIR"

echo "LineWatch configuration"
echo
echo "Use any existing FRITZ!Box user that has permission to access FRITZ!Box settings."
echo "Creating a dedicated user is optional."
echo

read -r -p "FRITZ!Box username: " FRITZ_USER_INPUT
if [ -z "$FRITZ_USER_INPUT" ]; then
  echo "Username cannot be empty."
  exit 1
fi

read -r -s -p "FRITZ!Box password: " FRITZ_PASSWORD_INPUT
echo
if [ -z "$FRITZ_PASSWORD_INPUT" ]; then
  echo "Password cannot be empty."
  exit 1
fi

read -r -p "FRITZ!Box IPv4 address [auto-detect]: " FRITZ_HOST_INPUT

python3 - "$FRITZ_USER_INPUT" "$FRITZ_PASSWORD_INPUT" "$FRITZ_HOST_INPUT" <<'PY'
import shlex
import sys
from pathlib import Path

user, password, host = sys.argv[1:4]
path = Path(".env")
defaults = {
    "FRITZ_USER": user,
    "FRITZ_PASSWORD": password,
    "FRITZ_HOST": host,
    "LINEWATCH_INTERFACE": "eth0",
    "LINEWATCH_POLL_SECONDS": "2",
    "LINEWATCH_HEALTHY_PERSIST_SECONDS": "30",
    "LINEWATCH_FRITZ_POLL_SECONDS": "10",
    "LINEWATCH_PUBLIC_IP_SECONDS": "300",
    "LINEWATCH_RING_SECONDS": "120",
    "LINEWATCH_PING_TARGETS": "1.1.1.1,8.8.8.8",
    "LINEWATCH_DNS_NAME": "www.cloudflare.com",
    "LINEWATCH_HTTP_URL": "https://connectivitycheck.gstatic.com/generate_204",
}
with path.open("w", encoding="utf-8") as f:
    for key, value in defaults.items():
        f.write(f"{key}={shlex.quote(value)}\n")
PY

chmod 600 .env
echo
echo "Configuration saved to $APP_DIR/.env"
