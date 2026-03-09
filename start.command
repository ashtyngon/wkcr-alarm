#!/bin/bash
# ============================================================
#  WKCR Radio Alarm — double-click this file to start
# ============================================================

cd "$(dirname "$0")"

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║   WKCR Radio Alarm                   ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
  echo "  Python 3 is required."
  echo "  Install it from https://python.org/downloads"
  echo ""
  read -p "  Press Enter to close..."
  exit 1
fi

# Install dependencies if needed
if ! python3 -c "import flask" 2>/dev/null; then
  echo "  Installing dependencies (one-time setup)..."
  echo ""
  pip3 install flask pychromecast apscheduler --break-system-packages 2>/dev/null \
    || pip3 install flask pychromecast apscheduler
  echo ""
fi

echo "  Starting alarm server..."
echo "  Your browser will open automatically."
echo ""
echo "  Leave this window open in the background."
echo "  Press Ctrl+C to stop."
echo ""

python3 app.py
