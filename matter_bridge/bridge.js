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
let deviceName = null;

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
      id: "chechoo-radio-main",
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
