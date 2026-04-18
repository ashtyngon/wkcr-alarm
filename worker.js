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

// Lazy: Cloudflare Workers disallow crypto.randomUUID() at module
// load time. We generate on first request and cache in the isolate,
// so it stays stable within one Worker instance but regenerates on
// a fresh deploy/cold-start. Dashboard polls /api/version for this.
let _workerVersion = null;
function getWorkerVersion() {
  if (!_workerVersion) _workerVersion = crypto.randomUUID();
  return _workerVersion;
}

// Default CMS settings when nothing has been written to KV yet.
const DEFAULT_SETTINGS = {
  brightness: 100,          // 10-100, applied as black-overlay opacity on body
  paused: false,            // true = stop carousel rotation (legacy; unused in v6)
  force_panel: null,        // legacy (unused in v6); kept for backward compat
  show_slogan: false,       // show Lenin + rotating slogan ticker (default off)
  show_footer: true,        // show sunrise/sunset/live footer
  dark_mode: false,         // inverts palette (cream↔ink, red stays red)
  reload_token: 0,          // bumped by /control "Reload Wall" button
  mode: 'dashboard',        // 'dashboard' | 'clock' | 'poster' | 'weather'
};

const MODES = new Set(['dashboard', 'briefing', 'clock', 'poster', 'weather']);

// Per-line realtime GTFS-RT feed URLs (MTA NYCT).
// https://api.mta.info/#/subwayRealTimeFeeds
const FEEDS = {
  L: "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-l",
  G: "https://api-endpoint.mta.info/Dataservice/mtagtfsfeeds/nyct%2Fgtfs-g",
};

// Station config — AUDITED against MTA's GTFS static stops.txt.
// Each station has:
//   line   — which feed to pull from ("L" or "G")
//   stopN  — northbound / "first-stop-ward" platform stop_id
//   stopS  — southbound / "last-stop-ward" platform stop_id
//
// Stop IDs corrected after prior bug where Nassau Av (G train) was
// mislabeled L13 (actual: Montrose Av), Graham Av mislabeled L15
// (actual: Jefferson St), and Bedford Av mislabeled L17 (actual:
// Myrtle-Wyckoff Avs). Current values verified against MTA's
// published stop codes:
//   https://new.mta.info/maps/subway-line-maps
const STATIONS = [
  { name: "Nassau Av",  line: "G", stopN: "G28N", stopS: "G28S" },
  { name: "Graham Av",  line: "L", stopN: "L11N", stopS: "L11S" },
  { name: "Bedford Av", line: "L", stopN: "L08N", stopS: "L08S" },
];

// Direction labels per line. "N" and "S" suffixes in GTFS stop_ids
// are relative to the route (first stop / last stop), NOT compass.
// L line: 8 Av (N) ↔ Rockaway Pkwy/Canarsie (S)
// G line: Court Sq/Queens (N) ↔ Church Av/south Brooklyn (S)
const DIRECTIONS = {
  L: {
    N: { label: "To Manhattan",    terminus: "8 Av",            arrow: "left"  },
    S: { label: "To Canarsie",     terminus: "Rockaway Pkwy",   arrow: "right" },
  },
  G: {
    N: { label: "To Queens",       terminus: "Court Sq",        arrow: "left"  },
    S: { label: "To S. Brooklyn",  terminus: "Church Av",       arrow: "right" },
  },
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

// Parse one feed's protobuf bytes into {stopArrivals, alerts}.
// stopArrivals: { stop_id: [eta_sec, ...] }
// alerts: [{ header, description }]
// Alerts are filtered by the allowedRoutes set (e.g. {"L"} or {"G"}).
function parseFeed(rawBytes, allowedRoutes) {
  const nowSec = Math.floor(Date.now() / 1000);
  const feed = parseMessage(rawBytes);

  // FeedMessage.entity = field 2 (repeated FeedEntity)
  const entities = allBytes(feed, 2);
  const stopArrivals = {};
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
        (stopArrivals[stopId] ||= []).push(eta);
      }
    }

    // ── FeedEntity.alert = field 5 ───────────────────────────────
    const alertBytes = firstBytes(ent, 5);
    if (alertBytes) {
      const alert = parseMessage(alertBytes);
      // Alert.informed_entity = field 5 (repeated EntitySelector)
      const ies = allBytes(alert, 5);
      let mentionsAllowed = false;
      for (const ieBytes of ies) {
        const ie = parseMessage(ieBytes);
        // EntitySelector.route_id = field 2 (string)
        const routeIdBytes = firstBytes(ie, 2);
        if (routeIdBytes) {
          const routeId = new TextDecoder().decode(routeIdBytes);
          if (allowedRoutes.has(routeId)) { mentionsAllowed = true; break; }
        }
      }
      if (!mentionsAllowed) continue;

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

  return { stopArrivals, alerts };
}

// Fetch one feed and parse it.
async function fetchAndParseFeed(line) {
  const url = FEEDS[line];
  const r = await fetch(url, {
    headers: { "User-Agent": "sensory-radio-worker/1.0" },
    cf: { cacheTtl: 15, cacheEverything: true },
  });
  if (!r.ok) throw new Error(`${line} feed ${r.status}`);
  const raw = new Uint8Array(await r.arrayBuffer());
  return parseFeed(raw, new Set([line]));
}

// Coordinate: fetch every configured feed (de-duped), extract arrivals
// for every configured station, and merge alerts.
async function extractAllArrivals() {
  const nowSec = Math.floor(Date.now() / 1000);
  const neededLines = [...new Set(STATIONS.map(s => s.line))];

  const results = await Promise.all(
    neededLines.map(async (line) => {
      try {
        return { line, data: await fetchAndParseFeed(line), error: null };
      } catch (e) {
        return { line, data: { stopArrivals: {}, alerts: [] }, error: String(e) };
      }
    })
  );

  const byLine = Object.fromEntries(results.map(r => [r.line, r]));

  const stations = STATIONS.map(conf => {
    const bucket = byLine[conf.line]?.data?.stopArrivals || {};
    const n = (bucket[conf.stopN] || []).sort((a, b) => a - b).slice(0, 8);
    const s = (bucket[conf.stopS] || []).sort((a, b) => a - b).slice(0, 8);
    return {
      name:  conf.name,
      line:  conf.line,
      directions: {
        N: { ...DIRECTIONS[conf.line].N, trains: n.map(e => Math.round(e / 60)) },
        S: { ...DIRECTIONS[conf.line].S, trains: s.map(e => Math.round(e / 60)) },
      },
    };
  });

  // Merge + dedupe alerts from all feeds
  const allAlerts = results.flatMap(r => r.data.alerts);
  const seenHeaders = new Set();
  const uniqueAlerts = allAlerts.filter(a => {
    if (seenHeaders.has(a.header)) return false;
    seenHeaders.add(a.header);
    return true;
  });

  // Surface feed errors so the dashboard can show a warning
  const feedErrors = results.filter(r => r.error).map(r => ({ line: r.line, error: r.error }));

  return {
    stations,
    alerts: uniqueAlerts,
    fetched_at: nowSec,
    feed_errors: feedErrors,
  };
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
    const data = await extractAllArrivals();
    return json({ ok: true, data }, 200, 15);
  } catch (e) {
    return json({ ok: false, error: String(e) }, 502);
  }
}

// ─── /api/debug ──────────────────────────────────────────────────────
// Returns ALL stop_ids encountered in every feed we fetch, with
// sample arrival minutes. Use this to verify which stop_ids map to
// which station names — protects against the Nassau-Av-on-the-L bug.
async function handleDebug() {
  try {
    const neededLines = [...new Set(STATIONS.map(s => s.line))];
    const results = await Promise.all(
      neededLines.map(async (line) => {
        const data = await fetchAndParseFeed(line);
        const sample = {};
        for (const [stopId, etas] of Object.entries(data.stopArrivals)) {
          sample[stopId] = etas.sort((a, b) => a - b).slice(0, 3)
            .map(e => Math.round(e / 60) + 'm');
        }
        return {
          line,
          num_stops_with_arrivals: Object.keys(data.stopArrivals).length,
          sample_by_stop_id: sample,
          alerts: data.alerts,
        };
      })
    );
    const matched = STATIONS.map(conf => {
      const feed = results.find(r => r.line === conf.line);
      const sN = feed?.sample_by_stop_id[conf.stopN];
      const sS = feed?.sample_by_stop_id[conf.stopS];
      return {
        ...conf,
        stopN_found: !!sN, stopN_sample: sN || null,
        stopS_found: !!sS, stopS_sample: sS || null,
      };
    });
    return json({ ok: true, feeds: results, station_audit: matched }, 200);
  } catch (e) {
    return json({ ok: false, error: String(e) }, 502);
  }
}

// ─── Router ──────────────────────────────────────────────────────────
// ─── /api/version ────────────────────────────────────────────────
//  Small heartbeat endpoint the dashboard polls every ~30s so it
//  can auto-reload when a new build has been deployed.
function handleVersion() {
  return json({ version: getWorkerVersion() }, 200, 0);
}

// ─── /api/settings ───────────────────────────────────────────────
//  GET  — returns current CMS settings (brightness, paused, etc)
//  POST — merges provided fields into the stored settings object
//  Settings live in Cloudflare KV under the single key "state".
async function handleSettings(request, env) {
  if (!env.SETTINGS) {
    // KV not bound yet — return defaults, reject writes politely
    if (request.method === 'POST') {
      return json({ ok: false, error: 'SETTINGS KV not bound' }, 501);
    }
    return json({ ok: true, data: DEFAULT_SETTINGS, note: 'KV not yet bound' });
  }

  if (request.method === 'GET') {
    const stored = await env.SETTINGS.get('state', { type: 'json' });
    return json({ ok: true, data: { ...DEFAULT_SETTINGS, ...(stored || {}) } });
  }

  if (request.method === 'POST' || request.method === 'PUT') {
    let body;
    try { body = await request.json(); } catch { return json({ ok: false, error: 'invalid json' }, 400); }
    // Whitelist & coerce fields so rogue POSTs can't pollute KV
    const current = (await env.SETTINGS.get('state', { type: 'json' })) || {};
    const merged = {
      ...DEFAULT_SETTINGS,
      ...current,
      ...(body.brightness    != null ? { brightness:    Math.max(10, Math.min(100, Number(body.brightness))) } : {}),
      ...(body.paused        != null ? { paused:        !!body.paused      } : {}),
      ...(body.force_panel   !== undefined ? { force_panel:   body.force_panel || null } : {}),
      ...(body.show_slogan   != null ? { show_slogan:   !!body.show_slogan  } : {}),
      ...(body.show_footer   != null ? { show_footer:   !!body.show_footer  } : {}),
      ...(body.dark_mode     != null ? { dark_mode:     !!body.dark_mode    } : {}),
      // reload_token: accept any numeric value; typically Date.now()
      ...(body.reload_token  != null ? { reload_token:  Number(body.reload_token) || 0 } : {}),
      // mode: restrict to whitelist so rogue POSTs can't break the wall
      ...(body.mode          != null ? { mode: MODES.has(body.mode) ? body.mode : 'dashboard' } : {}),
    };
    await env.SETTINGS.put('state', JSON.stringify(merged));
    return json({ ok: true, data: merged });
  }

  return json({ ok: false, error: 'method not allowed' }, 405);
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname === "/api/weather")  return handleWeather();
    if (url.pathname === "/api/trains")   return handleTrains();
    if (url.pathname === "/api/debug")    return handleDebug();
    if (url.pathname === "/api/version")  return handleVersion();
    if (url.pathname === "/api/settings") return handleSettings(request, env);

    // Pretty paths
    if (url.pathname === "/dashboard") {
      const rewrite = new Request(new URL("/dashboard.html", url).toString(), request);
      return env.ASSETS.fetch(rewrite);
    }
    if (url.pathname === "/control") {
      const rewrite = new Request(new URL("/control.html", url).toString(), request);
      return env.ASSETS.fetch(rewrite);
    }

    // Everything else → static assets
    return env.ASSETS.fetch(request);
  },
};
