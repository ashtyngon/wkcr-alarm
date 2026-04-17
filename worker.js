// ═══════════════════════════════════════════════════════════════════
//  sensory-radio Worker
//  Serves the /web static assets (radio player + dashboard) AND two
//  lightweight JSON endpoints that feed the wall dashboard:
//    /api/weather  →  Open-Meteo, same shape as the Pi's Flask endpoint
//    /api/trains   →  MTA GTFS-RT L-line feed decoded to JSON
//
//  Same origin as the dashboard, so no CORS dance on the client.
//  Response shape is kept identical to the Pi backend so the same
//  dashboard.html works against either.
// ═══════════════════════════════════════════════════════════════════

const DASH_LAT = 40.724;
const DASH_LON = -73.951;
const MTA_L_FEED = "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-l";

// Station name → { N: manhattan-bound stop_id, S: canarsie-bound stop_id }
const L_STATIONS = {
  "Nassau Av":  { N: "L13N", S: "L13S" },
  "Graham Av":  { N: "L15N", S: "L15S" },
  "Bedford Av": { N: "L17N", S: "L17S" },
};

// ─── Minimal GTFS-RT protobuf decoder ────────────────────────────────
//
// We only need three fields, so we hand-roll the bare minimum of the
// protobuf wire format instead of shipping protobufjs (~100KB).
//
// Wire format: each field = (tag<<3 | wire_type) varint, followed by
// a value whose encoding depends on wire_type.
//   wire 0 = varint
//   wire 2 = length-delimited (string, bytes, sub-message)
// We ignore other wire types — GTFS-RT doesn't use fixed-32/-64
// in the fields we care about.
// ──────────────────────────────────────────────────────────────────────
function readVarint(buf, i) {
  let result = 0n, shift = 0n;
  while (i < buf.length) {
    const b = buf[i++];
    result |= BigInt(b & 0x7f) << shift;
    if ((b & 0x80) === 0) return [result, i];
    shift += 7n;
  }
  throw new Error("varint truncated");
}

// Returns { [tag]: [ { wire, val } ] } where val is either BigInt
// (wire 0) or Uint8Array slice (wire 2). Unsupported wires are skipped.
function parseMessage(buf) {
  const fields = {};
  let i = 0;
  while (i < buf.length) {
    const [tw, ni] = readVarint(buf, i); i = ni;
    const tag = Number(tw >> 3n);
    const wire = Number(tw & 7n);
    let val;
    if (wire === 0) {
      const [v, ni2] = readVarint(buf, i); val = v; i = ni2;
    } else if (wire === 2) {
      const [lenBig, ni2] = readVarint(buf, i);
      const len = Number(lenBig);
      val = buf.subarray(ni2, ni2 + len);
      i = ni2 + len;
    } else if (wire === 1) {
      i += 8; continue;  // skip fixed64
    } else if (wire === 5) {
      i += 4; continue;  // skip fixed32
    } else {
      throw new Error("unknown wire type " + wire);
    }
    (fields[tag] ||= []).push({ wire, val });
  }
  return fields;
}

function firstBytes(fields, tag) { return fields[tag]?.[0]?.val; }
function allBytes(fields, tag)   { return (fields[tag] || []).map(f => f.val); }
function firstVarint(fields, tag) { return fields[tag]?.[0]?.val; }

// Given the raw L-line GTFS-RT protobuf bytes, return an object shaped
// like the Pi's /api/trains response.
function extractLArrivals(rawBytes) {
  const nowSec = Math.floor(Date.now() / 1000);
  const feed = parseMessage(rawBytes);

  // FeedMessage.entity = field 2 (repeated FeedEntity)
  const entities = allBytes(feed, 2);
  const stopMap = {}; // stop_id -> [eta_sec, ...]

  for (const entBytes of entities) {
    const ent = parseMessage(entBytes);
    // FeedEntity.trip_update = field 3 (TripUpdate)
    const tuBytes = firstBytes(ent, 3);
    if (!tuBytes) continue;
    const tu = parseMessage(tuBytes);
    // TripUpdate.stop_time_update = field 2 (repeated StopTimeUpdate)
    const stus = allBytes(tu, 2);
    for (const stuBytes of stus) {
      const stu = parseMessage(stuBytes);
      // StopTimeUpdate.stop_id = field 4 (string)
      const stopIdBytes = firstBytes(stu, 4);
      if (!stopIdBytes) continue;
      const stopId = new TextDecoder().decode(stopIdBytes);
      // Prefer arrival (field 2), fall back to departure (field 1? — actually
      // StopTimeUpdate.arrival = 2, departure = 3 in GTFS-RT spec).
      const arrivalBytes  = firstBytes(stu, 2);
      const departureBytes = firstBytes(stu, 3);
      const teBytes = arrivalBytes || departureBytes;
      if (!teBytes) continue;
      const te = parseMessage(teBytes);
      // StopTimeEvent.time = field 2 (int64)
      const timeField = firstVarint(te, 2);
      if (timeField == null) continue;
      const eta = Number(timeField) - nowSec;
      if (eta < 0) continue;
      (stopMap[stopId] ||= []).push(eta);
    }
  }

  const stations = [];
  for (const [name, dirs] of Object.entries(L_STATIONS)) {
    const n = (stopMap[dirs.N] || []).sort((a, b) => a - b).slice(0, 8);
    const s = (stopMap[dirs.S] || []).sort((a, b) => a - b).slice(0, 8);
    stations.push({
      name,
      manhattan_bound: n.map(e => Math.round(e / 60)),
      canarsie_bound:  s.map(e => Math.round(e / 60)),
    });
  }
  return { stations, fetched_at: nowSec };
}

// ─── JSON response helpers ───────────────────────────────────────────
function json(obj, status = 200, cacheSec = 0) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": cacheSec > 0 ? `public, max-age=${cacheSec}` : "no-store",
    },
  });
}

// ─── /api/weather ────────────────────────────────────────────────────
async function handleWeather() {
  const params = new URLSearchParams({
    latitude:  DASH_LAT.toString(),
    longitude: DASH_LON.toString(),
    current:   "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,is_day",
    hourly:    "temperature_2m,weather_code,precipitation_probability",
    daily:     "weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset",
    temperature_unit: "fahrenheit",
    wind_speed_unit:  "mph",
    timezone:         "America/New_York",
    forecast_days:    "2",
  });
  try {
    const r = await fetch("https://api.open-meteo.com/v1/forecast?" + params, {
      headers: { "User-Agent": "sensory-radio-worker/1.0" },
      cf: { cacheTtl: 600, cacheEverything: true },
    });
    if (!r.ok) return json({ ok: false, error: `Open-Meteo ${r.status}` }, 502);
    const data = await r.json();
    return json({ ok: true, data }, 200, 300);
  } catch (e) {
    return json({ ok: false, error: String(e) }, 502);
  }
}

// ─── /api/trains ─────────────────────────────────────────────────────
async function handleTrains() {
  try {
    const r = await fetch(MTA_L_FEED, {
      headers: { "User-Agent": "sensory-radio-worker/1.0" },
      cf: { cacheTtl: 15, cacheEverything: true },
    });
    if (!r.ok) return json({ ok: false, error: `MTA ${r.status}` }, 502);
    const raw = new Uint8Array(await r.arrayBuffer());
    const data = extractLArrivals(raw);
    return json({ ok: true, data }, 200, 15);
  } catch (e) {
    return json({ ok: false, error: String(e) }, 502);
  }
}

// ─── Router ──────────────────────────────────────────────────────────
export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/api/weather") return handleWeather();
    if (url.pathname === "/api/trains")  return handleTrains();

    // Pretty path: /dashboard → serve /dashboard.html from assets
    if (url.pathname === "/dashboard") {
      const rewrite = new Request(new URL("/dashboard.html", url).toString(), request);
      return env.ASSETS.fetch(rewrite);
    }

    // Everything else → static assets (radio player at /, stations.json, etc)
    return env.ASSETS.fetch(request);
  },
};
