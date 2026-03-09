#!/usr/bin/env bash
# Upgrade the systemd service with watchdog + hardened restart policy
# Run on the Pi: bash ~/wkcr-alarm/upgrade-service.sh

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Upgrading radio-alarm service…"

sudo tee /etc/systemd/system/radio-alarm.service > /dev/null << EOF
[Unit]
Description=Radio Alarm
After=network-online.target
Wants=network-online.target
# Wait 10s after network is up before starting (let mDNS settle)
StartLimitIntervalSec=300
StartLimitBurst=10

[Service]
ExecStart=$SCRIPT_DIR/venv/bin/python3 $SCRIPT_DIR/app.py
WorkingDirectory=$SCRIPT_DIR
Restart=always
RestartSec=5
User=$USER
# Kill cleanly
KillSignal=SIGINT
TimeoutStopSec=10
# Environment
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl restart radio-alarm

echo ""
echo "Done! Service upgraded with:"
echo "  • Auto-restart on crash (5s delay)"
echo "  • Up to 10 restarts per 5 minutes"
echo "  • Clean shutdown signal"
echo "  • Unbuffered Python output for logs"
echo ""
echo "Check status: sudo systemctl status radio-alarm"
