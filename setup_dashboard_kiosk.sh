#!/bin/bash
# Run this ONCE on the Pi to turn it into a wall-mounted kiosk for
# the Sensory Dashboard. It:
#   - installs unclutter (hides mouse cursor when idle)
#   - configures LightDM to auto-login as pi with the openbox session
#     (lightest WM available; Pi Zero 2 W's 425MB RAM needs the savings)
#   - writes an openbox autostart that:
#       * disables screen blanking / DPMS
#       * launches Chromium in kiosk mode pointing at the local dashboard
#       * hides the mouse cursor
# After running, plug in a monitor to the Pi's HDMI and reboot.
# Re-running is safe (idempotent).

set -e

DASHBOARD_URL="http://localhost:8550/dashboard"
USER_NAME="pi"

echo "==> 1/4  Installing unclutter (hides mouse cursor)…"
if ! command -v unclutter >/dev/null; then
  sudo apt-get update -q
  sudo apt-get install -y unclutter
else
  echo "    unclutter already installed"
fi

echo "==> 2/4  Configuring LightDM auto-login (openbox session)…"
sudo tee /etc/lightdm/lightdm.conf.d/10-kiosk-autologin.conf >/dev/null <<EOF
# Auto-login pi into a minimal openbox session for the kiosk dashboard
[Seat:*]
autologin-user=${USER_NAME}
autologin-user-timeout=0
autologin-session=openbox
user-session=openbox
EOF

echo "==> 3/4  Writing openbox autostart…"
mkdir -p /home/${USER_NAME}/.config/openbox
tee /home/${USER_NAME}/.config/openbox/autostart >/dev/null <<'EOF'
#!/bin/bash
# Openbox autostart — runs once when pi's X session starts.

# Disable screen blanking / DPMS so the wall display stays on 24/7
xset s off
xset -dpms
xset s noblank

# Hide the mouse cursor after 1 second of idle
unclutter -idle 1 -root &

# Wait a couple seconds for the Flask service to be ready on boot
# (the radio-alarm systemd unit starts around the same time)
sleep 5

# Launch Chromium in kiosk mode. --noerrdialogs and --disable-infobars
# suppress the "Restore tabs?" popup and the top warning strip.
# --disable-features=TranslateUI stops the translate popover.
# On a Pi Zero 2 W, leave GPU accel on (helps smooth scrolling).
chromium \
  --kiosk \
  --noerrdialogs \
  --disable-infobars \
  --disable-session-crashed-bubble \
  --disable-features=TranslateUI \
  --no-first-run \
  --autoplay-policy=no-user-gesture-required \
  --incognito \
  "http://localhost:8550/dashboard" &
EOF
chmod +x /home/${USER_NAME}/.config/openbox/autostart
chown -R ${USER_NAME}:${USER_NAME} /home/${USER_NAME}/.config/openbox

echo "==> 4/4  Ensuring graphical target is default…"
sudo systemctl set-default graphical.target

echo ""
echo "════════════════════════════════════════════════════════════"
echo "Setup complete."
echo ""
echo "Next:  1. Plug an HDMI monitor into the Pi"
echo "       2. sudo reboot"
echo ""
echo "The dashboard will appear automatically ~45s after boot."
echo "To manage the Pi remotely, SSH still works — the dashboard"
echo "just runs on top of the existing radio-alarm service."
echo ""
echo "To remove: sudo rm /etc/lightdm/lightdm.conf.d/10-kiosk-autologin.conf"
echo "           then: sudo reboot"
echo "════════════════════════════════════════════════════════════"
