#!/bin/bash
# ============================================================
#  Radio Alarm — Raspberry Pi Installer
#  Run this ONCE after you copy the folder to your Pi.
#  It installs everything and sets the alarm to start on boot.
# ============================================================

set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║   Radio Alarm — Installing...        ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

# 1. System packages
echo "  [1/4] Installing system packages..."
sudo apt-get update -qq
sudo apt-get install -y -qq python3-pip python3-venv avahi-daemon > /dev/null 2>&1
echo "         Done."

# 2. Python dependencies (in a venv to keep things clean)
echo "  [2/4] Installing Python libraries..."
python3 -m venv "$SCRIPT_DIR/venv"
"$SCRIPT_DIR/venv/bin/pip" install --quiet flask pychromecast apscheduler
echo "         Done."

# 3. Create systemd service (auto-start on boot)
echo "  [3/4] Setting up auto-start..."
sudo tee /etc/systemd/system/radio-alarm.service > /dev/null << EOF
[Unit]
Description=Radio Alarm
After=network-online.target
Wants=network-online.target

[Service]
ExecStart=$SCRIPT_DIR/venv/bin/python3 $SCRIPT_DIR/app.py
WorkingDirectory=$SCRIPT_DIR
Restart=always
RestartSec=10
User=$USER

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable radio-alarm
sudo systemctl start radio-alarm
echo "         Done."

# 4. Install Tailscale (so you can access from anywhere)
echo "  [4/4] Installing Tailscale (remote access)..."
if ! command -v tailscale &> /dev/null; then
    curl -fsSL https://tailscale.com/install.sh | sh
    echo ""
    echo "  ┌─────────────────────────────────────────────────┐"
    echo "  │  Tailscale installed! Run this to connect:       │"
    echo "  │                                                  │"
    echo "  │    sudo tailscale up                             │"
    echo "  │                                                  │"
    echo "  │  It will give you a link to sign in.             │"
    echo "  │  After that, you can access the alarm from       │"
    echo "  │  anywhere using your Tailscale IP.               │"
    echo "  └─────────────────────────────────────────────────┘"
else
    echo "         Tailscale already installed."
fi

echo ""
echo "  ╔══════════════════════════════════════════════════╗"
echo "  ║   All done!                                      ║"
echo "  ║                                                  ║"
echo "  ║   Open this on your phone or laptop:             ║"
echo "  ║                                                  ║"
echo "  ║     http://raspberrypi.local:8550                ║"
echo "  ║                                                  ║"
echo "  ║   (If that doesn't work, try your Pi's IP.)      ║"
echo "  ╚══════════════════════════════════════════════════╝"
echo ""
