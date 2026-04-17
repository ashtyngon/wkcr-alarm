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
// like the Pi's /api/trains response. Also extracts service alerts
// (delays, suspensions) so the dashboard can surface them.
function extractLArrivals(rawBytes) {
  const nowSec = Math.floor(Date.now() / 1000);
  const feed = parseMessage(rawBytes);

  // FeedMessage.entity = field 2 (repeated FeedEntity)
  const entities = allBytes(feed, 2);
  const stopMap = {}; // stop_id -> [eta_sec, ...]
  const alerts = [];

  for (const entBytes of entities) {
    const ent = parseMessage(entBytes);

    // ── FeedEntity.trip_update = field 3 ─────────────────────────
    const tuBytes = firstBytes(ent, 3);
    if (tuBytes) {
      const tu = parseMessage(tuBytes);
      // TripUpdate.stop_time_update = field 2 (repeated)
      const stus = allBytes(tu, 2);
      for (const stuBytes of stus) {
        const stu = parseMessage(stuBytes);
        const stopIdBytes = firstBytes(stu, 4); // StopTimeUpdate.stop_id
        if (!stopIdBytes) continue;
        const stopId = new TextDecoder().decode(stopIdBytes);
        // arrival = 2, departure = 1 (both StopTimeEvent); prefer arrival
        const arrivalBytes  = firstBytes(stu, 2);
        const departureBytes = firstBytes(stu, 1);
        const teBytes = arrivalBytes || departureBytes;
        if (!teBytes) continue;
        const te = parseMessage(teBytes);
        const timeField = firstVarint(te, 2); // StopTimeEvent.time (int64)
        if (timeField == null) continue;
        const eta = Number(timeField) - nowSec;
        if (eta < 0) continue;
        (stopMap[stopId] ||= []).push(eta);
      }
    }

    // ── FeedEntity.alert = field 5 ───────────────────────────────
    const alertBytes = firstBytes(ent, 5);
    if (alertBytes) {
      const alert = parseMessage(alertBytes);
      // Alert.informed_entity = field 5 (repeated EntitySelector)
      const ies = allBytes(alert, 5);
      let mentionsL = false;
      for (const ieBytes of ies) {
        const ie = parseMessage(ieBytes);
        // EntitySelector.route_id = field 2 (string)
        const routeIdBytes = firstBytes(ie, 2);
        if (routeIdBytes) {
          const routeId = new TextDecoder().decode(routeIdBytes);
          if (routeId === 'L') { mentionsL = true; break; }
        }
      }
      if (!mentionsL) continue;

      // Alert.header_text = field 10 (TranslatedString)
      const headerTsBytes = firstBytes(alert, 10);
      // Alert.description_text = field 11 (TranslatedString)
      const descTsBytes   = firstBytes(alert, 11);

      const decodeTs = (tsBytes) => {
        if (!tsBytes) return '';
        const ts = parseMessage(tsBytes);
        // TranslatedString.translation = field 1 (repeated Translation)
        const translations = allBytes(ts, 1);
        for (const transBytes of translations) {
          const trans = parseMessage(transBytes);
          // Translation.text = field 1, Translation.language = field 2
          const textBytes = firstBytes(trans, 1);
          const langBytes = firstBytes(trans, 2);
          const lang = langBytes ? new TextDecoder().decode(langBytes) : 'en';
          if (textBytes && (lang === 'en' || lang === 'en-US' || lang === '')) {
            return new TextDecoder().decode(textBytes);
          }
        }
        return '';
      };

      const header = decodeTs(headerTsBytes);
      const description = decodeTs(descTsBytes);
      if (header) {
        alerts.push({ header, description });
      }
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

  // Dedupe alerts by header text (MTA often sends multiple with same header)
  const seenHeaders = new Set();
  const uniqueAlerts = alerts.filter(a => {
    if (seenHeaders.has(a.header)) return false;
    seenHeaders.add(a.header);
    return true;
  });

  return { stations, alerts: uniqueAlerts, fetched_at: nowSec };
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
    // Current conditions — add uv_index, dewpoint, precipitation for richer
    // cards when the dashboard rotates through "right now" views.
    current:   "temperature_2m,apparent_temperature,relative_humidity_2m,weather_code,wind_speed_10m,wind_direction_10m,is_day,uv_index,precipitation",
    hourly:    "temperature_2m,weather_code,precipitation_probability,uv_index",
    // Daily: pull full week so dashboard can rotate through 7 days.
    daily:     "weather_code,temperature_2m_max,temperature_2m_min,sunrise,sunset,uv_index_max,precipitation_probability_max,precipitation_sum,wind_speed_10m_max",
    temperature_unit: "fahrenheit",
    wind_speed_unit:  "mph",
    timezone:         "America/New_York",
    // 7 days of forecast for the rotating weather card.
    forecast_days:    "7",
    // Open-Meteo's "best_match" model blends ICON + GFS + ECMWF + AROME,
    // which is their most accurate setting for NYC (default, but explicit).
    models:           "best_match",
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
