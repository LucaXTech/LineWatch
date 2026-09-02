#!/usr/bin/env bash
set -euo pipefail

if [ "$(id -u)" -eq 0 ]; then
  echo "Run ./install.sh as your normal user, not with sudo."
  exit 1
fi

APP_DIR="$(cd "$(dirname "$0")" && pwd)"
USER_NAME="$(id -un)"

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
    echo "Created .env from .env.example; configure it before starting LineWatch."
  fi
fi

sudo tee /etc/systemd/system/linewatch.service >/dev/null <<EOF
[Unit]
Description=LineWatch FRITZ!Box connection monitor
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
Description=LineWatch web dashboard
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

if grep -q '^FRITZ_USER=$' "$APP_DIR/.env" 2>/dev/null; then
  echo
  echo "Configure .env, then run:"
  echo "  sudo systemctl start linewatch linewatch-dashboard"
else
  sudo systemctl restart linewatch linewatch-dashboard
  echo
  echo "LineWatch is running."
  echo "Open: http://$(hostname).local:8080"
fi
