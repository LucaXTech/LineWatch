#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -eq 0 ]; then
  echo "Run ./install.sh as your normal user, not with sudo."
  exit 1
fi

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
USER_NAME="$(id -un)"

if ! command -v apt-get >/dev/null 2>&1; then
  echo "Automatic installation currently supports Debian/Ubuntu/Raspberry Pi OS systems with apt."
  echo "For other Linux distributions, install Python 3, venv, iproute2 and ping manually, then use the manual setup instructions."
  exit 1
fi

sudo apt-get update
sudo apt-get install -y python3-venv iproute2 iputils-ping

python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install --upgrade pip
"$APP_DIR/.venv/bin/pip" install -r "$APP_DIR/requirements.txt"

chmod +x "$APP_DIR/configure.sh" "$APP_DIR/run_monitor.sh" "$APP_DIR/run_dashboard.sh"

if [ ! -f "$APP_DIR/.env" ]; then
  if [ -t 0 ]; then
    "$APP_DIR/configure.sh"
  else
    cp "$APP_DIR/.env.example" "$APP_DIR/.env"
    chmod 600 "$APP_DIR/.env"
    echo "Created .env from .env.example. UplinkWitness will start in generic mode unless FRITZ credentials are added."
  fi
fi

# Service identifiers intentionally retain the original linewatch names so
# existing installations can upgrade without replacing units or data paths.
sudo tee /etc/systemd/system/linewatch.service >/dev/null <<EOF
[Unit]
Description=UplinkWitness Internet connection monitor
Wants=network-online.target
After=network-online.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/run_monitor.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/linewatch-dashboard.service >/dev/null <<EOF
[Unit]
Description=UplinkWitness web dashboard
After=network-online.target linewatch.service
Wants=network-online.target

[Service]
Type=simple
User=$USER_NAME
WorkingDirectory=$APP_DIR
ExecStart=$APP_DIR/run_dashboard.sh
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable linewatch.service linewatch-dashboard.service
sudo systemctl restart linewatch linewatch-dashboard

echo
echo "UplinkWitness is running."
echo "Open: http://$(hostname).local:8080"
echo "If mDNS is unavailable, use this machine's LAN IP with port 8080."
