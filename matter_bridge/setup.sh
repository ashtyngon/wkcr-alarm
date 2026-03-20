#!/bin/bash
set -e

echo "=== Chechoo Radio Matter Bridge Setup ==="

# Check Node.js version
if ! command -v node &> /dev/null; then
    echo "Node.js not found. Install Node.js 20+ first:"
    echo "  curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -"
    echo "  sudo apt-get install -y nodejs"
    exit 1
fi

NODE_VER=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
if [ "$NODE_VER" -lt 20 ]; then
    echo "Node.js 20+ required (found $(node -v))"
    exit 1
fi

echo "Node.js $(node -v) found"

# Install dependencies
cd "$(dirname "$0")"
npm install

echo ""
echo "=== Setup complete ==="
echo ""
echo "To start the bridge:  cd matter_bridge && node bridge.js"
echo "To install as service: sudo cp chechoo-matter.service /etc/systemd/system/"
echo "                       sudo systemctl enable --now chechoo-matter"
echo ""
echo "After starting, open Google Home app -> Add device -> scan the QR code"
