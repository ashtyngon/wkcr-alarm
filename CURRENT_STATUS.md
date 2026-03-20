# WKCR Radio Alarm — Current Status

## What This Project Is
Radio alarm clock running on a Raspberry Pi Zero 2 W. Casts internet radio to Google Home speakers via pychromecast. Flask app on port 8550 serves both the API and web UI.

## Current State (March 9, 2026)
- **Deployed and working on Pi** — playback, stop, discovery, volume all verified
- 7 Google Home speakers discovered on network
- 50 internet radio stations with 9 genre filter pills
- Warm golden theme UI (rebuilt from recovered design + current backend)
- All pychromecast API compatibility issues resolved
- Git repo: github.com/ashtyngon/wkcr-alarm (needs push of latest fixes)

## Pi Connection Details
- SSH: `ssh pi@192.168.86.241` (password: betty)
- Web UI: http://192.168.86.241:8550
- Service: `radio-alarm.service` (systemd, enabled)
- App directory: `/home/pi/wkcr-alarm/`
- Python venv: `/home/pi/wkcr-alarm/venv/`

## Speakers on Network (7)
1. kitchen speaker (Google Nest Mini)
2. Bedroom speaker (Google Home Mini)
3. Kitchen Max (Google Home Max)
4. Living Room TV (Google TV Streamer)
5. Bedroom Wifi (Nest Wifi point)
6. Everywhere (Google Cast Group)
7. kitchen combo (Google Cast Group)

## Key Files
- app.py — Flask backend (~550 lines)
- ui.html — Web UI (~1060 lines, warm golden theme)
- config.json — Runtime config (created by app)
- install.sh — One-time Pi setup script

## Pychromecast API (Pi's version)
These are the correct APIs — do NOT change these:
- `discover_chromecasts()` → returns `CastInfo` objects with `.friendly_name`, `.model_name`
- `get_listed_chromecasts(friendly_names=[...], discovery_timeout=N)` → returns `Chromecast` objects
- `Chromecast` objects: `.name`, `.wait()`, `.media_controller`, `.set_volume()`, `.status.volume_level`
- `MediaController`: `.play_media()`, `.stop()`, `.block_until_active()`
- Do NOT use: `get_chromecasts()`, `.friendly_name` on Chromecast, `.wait_for_media_player()`

## Bugs Fixed (don't revert these)
1. save() POSTs config to backend (was localStorage only)
2. sendPlay() sends station_id + device_name (field names were wrong)
3. sendStop() sends JSON body with device_name (was empty)
4. Config path relative to app.py (was hardcoded /home/pi)
5. Day numbering mapped between UI (0=Sun) and Python (0=Mon)
6. checkServer() loads config from backend on page load
7. testAlarm() calls sendPlay()
8. Replaced 3 dead streams
9. `_get_cast()` uses `get_listed_chromecasts` (not `get_chromecasts`)
10. All cast references use `.name` (not `.friendly_name`)
11. All wait calls use `cast.wait()` (not `wait_for_media_player`)
12. No alarm fade-in (removed per user request)

## Architecture Notes
- Triple-layer stop: quit_app() + mc.stop() + STOP_GRACE_SECONDS
- Optimistic UI with stopRequested flag
- Three-phase cast cache: check(locked) → discover(unlocked) → store(locked)
- Alarm thread checks every 30 sec, uses _alarm_last_triggered_minute to prevent re-trigger
- Volume: UI integer 5-80, divided by 100.0 for Chromecast (0.0-1.0 scale)
