# Chechoo Radio — Matter Voice Control Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Enable Google Home voice control of the radio alarm app via Matter virtual devices, fully local on the LAN.

**Architecture:** A Node.js Matter bridge (`matter_bridge.js`) runs alongside the Flask app on the Pi. It registers 6 virtual devices as a Matter aggregator. When Google Home sends on/off/volume commands over the local network, the bridge calls the Flask API at `localhost:8550`. Also adds 2 new stations (WNYC, Sunshine Live) and fixes speaker auto-switch.

**Tech Stack:** Node.js 20+, `@matter/main`, existing Flask/pychromecast backend

---

### Task 1: Add new stations (WNYC, Sunshine Live)

**Files:**
- Modify: `app.py` (STATIONS list)
- Modify: `ui.html` (STATION_MOODS, GROUPS)

**Step 1: Add stations to app.py STATIONS list**

Add after the `# --- Eclectic ---` comment block, before `# --- Custom ---`:

```python
    # --- Talk / NPR ---
    {"id": "wnyc",          "name": "WNYC 93.9",              "genre": "NPR & public radio — New York City",           "url": "https://fm939.wnyc.org/wnycfm"},
    # --- Electronic / Techno ---
    {"id": "sunshinelive",  "name": "Sunshine Live",           "genre": "Techno, house & trance — Germany",             "url": "https://stream.sunshine-live.de/live/mp3-192/"},
```

**Step 2: Add mood mappings in ui.html**

In the `STATION_MOODS` object, add:
```javascript
  wnyc:['morning','indie'],
  sunshinelive:['groove'],
```

In the `GROUPS` array, add two new groups before `{ label: 'Other' }`:
```javascript
  { label: 'Talk / NPR',    ids: ['wnyc'] },
  { label: 'Techno',        ids: ['sunshinelive'] },
```

**Step 3: Verify stations appear in UI**

Run: `python3 app.py` and open `http://localhost:8550` — confirm WNYC and Sunshine Live appear.

**Step 4: Commit**

```bash
git add app.py ui.html
git commit -m "Add WNYC and Sunshine Live stations for voice control presets"
```

---

### Task 2: Create Matter bridge — package.json and project setup

**Files:**
- Create: `matter_bridge/package.json`

**Step 1: Create package.json**

```json
{
  "name": "chechoo-radio-matter-bridge",
  "version": "1.0.0",
  "type": "module",
  "description": "Matter bridge for Chechoo Radio — Google Home voice control",
  "main": "bridge.js",
  "scripts": {
    "start": "node bridge.js"
  },
  "dependencies": {
    "@matter/main": "^0.12.0"
  },
  "engines": {
    "node": ">=20.19.0 <22.0.0 || >=22.13.0"
  }
}
```

**Step 2: Install dependencies**

Run:
```bash
cd matter_bridge && npm install
```

Expected: `node_modules` created with `@matter/main` and its dependencies.

**Step 3: Commit**

```bash
git add matter_bridge/package.json
echo "node_modules" >> matter_bridge/.gitignore
git add matter_bridge/.gitignore
git commit -m "Add Matter bridge project skeleton"
```

---

### Task 3: Create Matter bridge — bridge.js

**Files:**
- Create: `matter_bridge/bridge.js`

**Step 1: Write the bridge script**

```javascript
import { Endpoint, Environment, ServerNode, VendorId } from "@matter/main";
import { BridgedDeviceBasicInformationServer } from "@matter/main/behaviors/bridged-device-basic-information";
import { OnOffLightDevice } from "@matter/main/devices/on-off-light";
import { DimmableLightDevice } from "@matter/main/devices/dimmable-light";
import { AggregatorEndpoint } from "@matter/main/endpoints/aggregator";

// --- Configuration ---
const FLASK_BASE = process.env.FLASK_URL || "http://localhost:8550";

const GENRE_DEVICES = [
  { id: "chechoo-french", label: "Chechoo French", stationId: "icichanson" },
  { id: "chechoo-jazz",   label: "Chechoo Jazz",   stationId: "swissjazz" },
  { id: "chechoo-npr",    label: "Chechoo NPR",    stationId: "wnyc" },
  { id: "chechoo-opera",  label: "Chechoo Opera",  stationId: "operafm" },
  { id: "chechoo-techno", label: "Chechoo Techno", stationId: "sunshinelive" },
];

// --- State ---
let currentStationId = null;
let currentVolume = 50;
let deviceName = null; // loaded from Flask config

// --- Flask API helpers ---
async function flaskGet(path) {
  const r = await fetch(`${FLASK_BASE}${path}`);
  return r.json();
}

async function flaskPost(path, body) {
  const r = await fetch(`${FLASK_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  return r.json();
}

async function loadConfig() {
  const data = await flaskGet("/config");
  deviceName = data.config?.device_name || "Living Room";
  currentVolume = data.config?.volume || 50;
  currentStationId = data.config?.station || "swissjazz";
  console.log(`Config loaded: device=${deviceName}, station=${currentStationId}, volume=${currentVolume}`);
}

async function playStation(stationId) {
  currentStationId = stationId;
  console.log(`Playing ${stationId} on ${deviceName} at volume ${currentVolume}`);
  return flaskPost("/play", {
    station_id: stationId,
    device_name: deviceName,
    volume: currentVolume,
  });
}

async function stopPlayback() {
  console.log(`Stopping playback on ${deviceName}`);
  return flaskPost("/stop", { device_name: deviceName });
}

async function setVolume(level254) {
  // Convert Matter level (1-254) to percent (1-100)
  currentVolume = Math.round((level254 / 254) * 100);
  currentVolume = Math.max(1, Math.min(100, currentVolume));
  console.log(`Volume set to ${currentVolume}%`);
  return flaskPost("/volume", {
    device_name: deviceName,
    volume: currentVolume,
  });
}

// --- Matter bridge setup ---
async function main() {
  await loadConfig();

  const server = await ServerNode.create({
    id: "chechoo-radio",
    network: { port: 5540 },
    commissioning: {
      passcode: 20242024,
      discriminator: 2712,
    },
    productDescription: {
      name: "Chechoo Radio",
      deviceType: AggregatorEndpoint.deviceType,
    },
    basicInformation: {
      vendorName: "Chechoo",
      vendorId: VendorId(0xfff1),
      nodeLabel: "Chechoo Radio",
      productName: "Chechoo Radio",
      productLabel: "Chechoo Radio",
      productId: 0x8000,
      serialNumber: "chechoo-001",
      uniqueId: "chechoo-radio-bridge",
    },
  });

  const aggregator = new Endpoint(AggregatorEndpoint, { id: "aggregator" });
  await server.add(aggregator);

  // --- Main device: Chechoo Radio (dimmable = on/off + volume) ---
  const mainDevice = new Endpoint(
    DimmableLightDevice.with(BridgedDeviceBasicInformationServer),
    {
      id: "chechoo-radio",
      bridgedDeviceBasicInformation: {
        nodeLabel: "Chechoo Radio",
        productName: "Chechoo Radio",
        productLabel: "Chechoo Radio",
        serialNumber: "chechoo-main",
        reachable: true,
      },
    },
  );
  await aggregator.add(mainDevice);

  mainDevice.events.onOff.onOff$Changed.on(async (value) => {
    if (value) {
      await playStation(currentStationId);
    } else {
      await stopPlayback();
    }
  });

  mainDevice.events.levelControl.currentLevel$Changed.on(async (value) => {
    if (value !== null && value !== undefined) {
      await setVolume(value);
    }
  });

  // --- Genre devices: on/off only ---
  for (const genre of GENRE_DEVICES) {
    const device = new Endpoint(
      OnOffLightDevice.with(BridgedDeviceBasicInformationServer),
      {
        id: genre.id,
        bridgedDeviceBasicInformation: {
          nodeLabel: genre.label,
          productName: genre.label,
          productLabel: genre.label,
          serialNumber: genre.id,
          reachable: true,
        },
      },
    );
    await aggregator.add(device);

    device.events.onOff.onOff$Changed.on(async (value) => {
      if (value) {
        await playStation(genre.stationId);
      } else {
        await stopPlayback();
      }
    });
  }

  console.log("Starting Chechoo Radio Matter bridge...");
  console.log("Commissioning passcode: 20242024");
  console.log("Open Google Home app → Add device → scan the QR code shown below");
  await server.run();
}

main().catch((e) => {
  console.error("Fatal error:", e);
  process.exit(1);
});
```

**Step 2: Test the bridge starts**

Run:
```bash
cd matter_bridge && node bridge.js
```

Expected: QR code printed to terminal, "Starting Chechoo Radio Matter bridge..." message, bridge listens on port 5540.

**Step 3: Commit**

```bash
git add matter_bridge/bridge.js
git commit -m "Add Matter bridge with 6 Chechoo Radio devices"
```

---

### Task 4: Create setup script and systemd service

**Files:**
- Create: `matter_bridge/setup.sh`
- Create: `matter_bridge/chechoo-matter.service`

**Step 1: Write setup script**

```bash
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
    echo "Node.js 20+ required (found v$(node -v))"
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
echo "After starting, open Google Home app → Add device → scan the QR code"
```

**Step 2: Write systemd service file**

```ini
[Unit]
Description=Chechoo Radio Matter Bridge
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=pi
WorkingDirectory=/home/pi/wkcr-alarm/matter_bridge
ExecStart=/usr/bin/node bridge.js
Restart=on-failure
RestartSec=10
Environment=FLASK_URL=http://localhost:8550

[Install]
WantedBy=multi-user.target
```

**Step 3: Make setup script executable and commit**

```bash
chmod +x matter_bridge/setup.sh
git add matter_bridge/setup.sh matter_bridge/chechoo-matter.service
git commit -m "Add setup script and systemd service for Matter bridge"
```

---

### Task 5: Fix speaker auto-switch (already done in ui.html)

**Files:**
- Modify: `ui.html` (speaker click handler)

**Step 1: Verify the fix**

The fix has already been applied. In the speaker card click handler, when a new speaker is selected while playing, `playNow()` is called automatically to switch playback.

**Step 2: Test**

1. Open UI, select a speaker, play a station
2. Select a different speaker
3. Confirm playback switches to the new speaker without manual play

**Step 3: Commit**

```bash
git add ui.html
git commit -m "Auto-switch playback when changing speakers while playing"
```

---

### Task 6: Update design doc and final commit

**Step 1: Verify everything works end-to-end**

1. Start Flask app: `python3 app.py`
2. Start Matter bridge: `cd matter_bridge && node bridge.js`
3. Confirm QR code appears
4. Commission in Google Home app
5. Test: "Hey Google, turn on Chechoo Jazz"
6. Test: "Hey Google, set Chechoo Radio to 40%"
7. Test: "Hey Google, turn off Chechoo Radio"

**Step 2: Final commit**

```bash
git add -A
git commit -m "Chechoo Radio: Matter voice control for Google Home"
```
