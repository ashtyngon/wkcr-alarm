import os
import json
import time
import threading
import logging
import re
from datetime import datetime
from flask import Flask, request, jsonify, send_file
import pychromecast

app = Flask(__name__)
LOG = logging.getLogger("radio")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

CONFIG_PATH = os.environ.get("RADIO_CONFIG", os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json"))
STOP_GRACE_SECONDS = 15

# --- Station list ---
STATIONS = [
    # --- Jazz ---
    {"id": "wkcr",          "name": "WKCR 89.9",              "genre": "Jazz & Classical — Columbia Univ., NYC",        "url": "http://wkcr.streamguys1.com/live"},
    {"id": "swissjazz",     "name": "Radio Swiss Jazz",       "genre": "Pure jazz, no talk — Switzerland",              "url": "https://stream.srg-ssr.ch/m/rsj/mp3_128"},
    {"id": "jazzradio",     "name": "Jazz Radio",             "genre": "Jazz — Lyon, France",                           "url": "https://jazzradio.ice.infomaniak.ch/jazzradio-high.mp3"},
    {"id": "tsfjazz",       "name": "TSF Jazz",               "genre": "Jazz institution — Paris, France",              "url": "https://tsfjazz.ice.infomaniak.ch/tsfjazz-high.mp3"},
    {"id": "abcjazz",       "name": "ABC Jazz",               "genre": "Jazz — ABC Australia, Melbourne",               "url": "https://live-radio01.mediahubaustralia.com/JAZW/mp3/"},
    {"id": "fipjazz",       "name": "FIP Jazz",               "genre": "Jazz — Radio France",                           "url": "https://icecast.radiofrance.fr/fipjazz-hifi.aac"},
    # --- Classical ---
    {"id": "swissclassic",  "name": "Radio Swiss Classic",    "genre": "Pure classical, no talk — Switzerland",         "url": "https://stream.srg-ssr.ch/m/rsc_de/mp3_128"},
    {"id": "nporadio4",     "name": "NPO Radio 4",            "genre": "Classical — Dutch public radio",                "url": "https://icecast.omroep.nl/radio4-bb-mp3"},
    {"id": "classicfm",     "name": "Classic FM",             "genre": "Classical — UK",                                "url": "https://media-ice.musicradio.com/ClassicFMMP3"},
    {"id": "wqxr",          "name": "WQXR",                   "genre": "Classical — New York City",                     "url": "https://stream.wqxr.org/wqxr"},
    {"id": "ancientfm",     "name": "Ancient FM",             "genre": "Medieval & Renaissance music",                  "url": "https://mediaserv73.live-streams.nl:18058/stream"},
    {"id": "wcpe",          "name": "WCPE Classical",         "genre": "24/7 classical, no commercials — NC",           "url": "https://audio-mp3.ibiblio.org:443/wcpe.mp3"},
    {"id": "abcclassic",    "name": "ABC Classic",            "genre": "Classical — ABC Australia, Melbourne",           "url": "https://live-radio01.mediahubaustralia.com/2FMW/mp3/"},
    {"id": "rai3",          "name": "RAI Radio 3",            "genre": "Classical & culture — RAI, Italy",              "url": "http://icestreaming.rai.it/3.mp3"},
    {"id": "naim",          "name": "Naim Classical",         "genre": "Audiophile classical — Naim Records, UK",       "url": "http://mscp3.live-streams.nl:8250/class-high.aac"},
    # --- Opera ---
    {"id": "operafm",       "name": "1.FM Opera House",       "genre": "Opera arias & performances — 24/7",            "url": "http://strm112.1.fm/opera_mobile_mp3"},
    {"id": "fmopera",       "name": "France Musique Opéra",   "genre": "French opera & vocal — Radio France",          "url": "https://icecast.radiofrance.fr/francemusiqueopera-hifi.aac"},
    {"id": "operavore",     "name": "WQXR Operavore",         "genre": "Curated opera — New York Public Radio",        "url": "http://opera-stream.wqxr.org/operavore-tunein"},
    {"id": "operamrg",      "name": "OperaRadio MRG.FM",      "genre": "Opera recordings & live performances",         "url": "http://listen.mrg.fm:8110/;"},
    {"id": "capriceopera",  "name": "Radio Caprice Opera",    "genre": "Opera — international repertoire",              "url": "http://79.120.39.202:8000/opera"},
    # --- Turkish / Anatolian ---
    {"id": "radyosiran",    "name": "Radyo Şiran",            "genre": "Turkish folk & türkü — Anatolia",              "url": "https://live.radyositesihazir.com/8078/stream"},
    {"id": "ankarahava",    "name": "Ankara Havaları",        "genre": "Turkish folk songs — Ankara, Turkey",          "url": "http://37.247.98.8/stream/30/;"},
    {"id": "turkishlove",   "name": "Love Radio Turkish",     "genre": "Turkish love songs & ballads",                 "url": "https://nl4.mystreaming.net/uber/lrturkish/icecast.audio"},
    # --- Persian / Iranian ---
    {"id": "radiofarda",    "name": "Radio Farda",            "genre": "Persian music & culture — RFE/RL",             "url": "http://rfe21.akacast.akamaistream.net/7/751/437779/v1/ibb.akacast.akamaistream.net/rfe21"},
    {"id": "iranintl",      "name": "Iran International",     "genre": "Persian contemporary — London",                "url": "https://radio.iraninternational.app/iintl_c"},
    # --- Armenian / Caucasian ---
    {"id": "yerevannights", "name": "Yerevan Nights",         "genre": "Armenian classics & folk — diaspora radio",    "url": "http://icecast.yerevannights.com/YerevanNights"},
    {"id": "radiojan",      "name": "Radio Jan",              "genre": "Armenian music — USA/diaspora",                "url": "https://s4.voscast.com:8865/stream"},
    # --- Greek ---
    {"id": "ertdeftero",    "name": "ERT Deftero",            "genre": "Greek folk, rebetiko, laïká — Athens",         "url": "https://radiostreaming.ert.gr/ert-deftero"},
    {"id": "ertkosmos",     "name": "ERT Kosmos",             "genre": "World music — Greek public radio",             "url": "https://radiostreaming.ert.gr/ert-kosmos"},
    {"id": "erttrito",      "name": "ERT Trito",              "genre": "Greek culture & classical — Athens",           "url": "https://radiostreaming.ert.gr/ert-trito"},
    # --- Arabic / North African ---
    {"id": "medi1tarab",    "name": "Medi1 Tarab",            "genre": "Arabic tarab & classical — Morocco",           "url": "http://live.medi1.com/Tarab"},
    {"id": "aswat",         "name": "Radio Aswat",            "genre": "Moroccan music & culture — Casablanca",        "url": "http://broadcast.ice.infomaniak.ch/aswat-high.mp3"},
    {"id": "radioliban",    "name": "Radio Liban Libre",      "genre": "Lebanese classics & Fairuz — Beirut",          "url": "https://edge.mixlr.com/channel/qtqeb"},
    # --- Indian / South Asian ---
    {"id": "somagoa",       "name": "SomaFM Suburbs of Goa",  "genre": "Desi-influenced world beats & tabla",         "url": "https://ice2.somafm.com/suburbsofgoa-128-mp3"},
    {"id": "ntsraga",       "name": "NTS Slow Focus",         "genre": "Raga, ambient & deep listening — London",      "url": "https://stream-mixtape-geo.ntslive.net/mixtape"},
    # --- Flamenco / Iberian ---
    {"id": "radioartflam",  "name": "RadioArt Flamenco",      "genre": "Pure flamenco guitar & cante — 24/7",         "url": "http://air.radioart.com/fFlamenco.mp3"},
    {"id": "sevillanas",    "name": "Radio Sevillanas",        "genre": "Sevillanas & Andalusian folk — Seville",      "url": "http://radio.wesped.com:8000/stream"},
    # --- Portuguese / Fado ---
    {"id": "radioamalia",   "name": "Rádio Amália",           "genre": "Fado & Portuguese soul — Lisbon",              "url": "http://centova.radio.com.pt:9496/;"},
    {"id": "fadocoimbra",   "name": "Fado de Coimbra",        "genre": "Coimbra fado tradition — Portugal",            "url": "https://nl.digitalrm.pt:8048/stream"},
    # --- Brazilian ---
    {"id": "somabossa",     "name": "SomaFM Bossa Beyond",    "genre": "Bossa nova, samba & MPB — 24/7",              "url": "https://ice2.somafm.com/bossa-128-mp3"},
    {"id": "bossajazzbr",   "name": "Bossa Jazz Brasil",      "genre": "Brazilian bossa & jazz — São Paulo",          "url": "https://centova5.transmissaodigital.com:20104/live"},
    # --- Argentine Tango ---
    {"id": "tangopasion",   "name": "Tango Pasión",           "genre": "Classic tango — Buenos Aires tradition",       "url": "http://nr11.newradio.it:9180/stream"},
    {"id": "tangobailar",   "name": "Tango Para Bailar",      "genre": "Tango for dancing — milonga classics",        "url": "http://stream.laut.fm/tangoparabailar"},
    # --- Celtic / Irish ---
    {"id": "celticmusic",   "name": "RadioArt Celtic",        "genre": "Celtic folk, fiddle & harp — 24/7",            "url": "http://air.radioart.com/fCeltic.mp3"},
    {"id": "irishpub",      "name": "Irish Pub Radio",        "genre": "Irish trad sessions & folk — Dublin",          "url": "http://solid24.streamupsolutions.com:8026/stream"},
    {"id": "somathistle",   "name": "SomaFM Thistle",         "genre": "Celtic & Scottish — fiddle, pipes, harp",     "url": "https://ice2.somafm.com/thistle-128-mp3"},
    # --- Balkan ---
    {"id": "capricebalkan", "name": "Radio Caprice Balkan",   "genre": "Balkan brass, folk & čoček",                   "url": "http://79.120.39.202:8000/balkan"},
    # --- French Chanson ---
    {"id": "icichanson",    "name": "ICI Chanson Française",  "genre": "French chanson 60s–today — Radio France",      "url": "https://icecast.radiofrance.fr/fbchansonfrancaise-hifi.aac"},
    {"id": "chantefrance",  "name": "Chante France",          "genre": "100% chanson française — ad-free",             "url": "http://stream.chantefrance.com/stream"},
    {"id": "croonerlove",   "name": "Crooner Radio Love",     "genre": "Romantic crooners & love ballads — Paris",     "url": "http://croonerradio_love.ice.infomaniak.ch/croonerradio-love-midfi.mp3"},
    {"id": "radionova",     "name": "Radio Nova",             "genre": "Eclectic soul, chanson, world — Paris",        "url": "http://novazz.ice.infomaniak.ch/novazz-128.mp3"},
    # --- Eclectic ---
    {"id": "fip",           "name": "FIP",                    "genre": "Eclectic, Jazz, World — Radio France, Paris",   "url": "https://icecast.radiofrance.fr/fip-hifi.aac"},
    {"id": "kexp",          "name": "KEXP 90.3",              "genre": "Indie & Eclectic — Seattle",                    "url": "https://kexp.streamguys1.com/kexp160.aac"},
    {"id": "nts1",          "name": "NTS 1",                  "genre": "Underground & Global — London",                 "url": "https://stream-relay-geo.ntslive.net/stream"},
    {"id": "nts2",          "name": "NTS 2",                  "genre": "Underground & Global — London",                 "url": "https://stream-relay-geo.ntslive.net/stream2"},
    {"id": "wfmu",          "name": "WFMU 91.1",              "genre": "Freeform — Jersey City, NJ",                    "url": "http://stream0.wfmu.org/freeform-128k"},
    {"id": "rp",            "name": "Radio Paradise",         "genre": "Eclectic — rock, world, jazz, classical",       "url": "http://stream.radioparadise.com/mp3-192"},
    {"id": "fipnouv",       "name": "FIP Nouveautés",         "genre": "New releases & discoveries — Radio France",     "url": "https://icecast.radiofrance.fr/fipnouveautes-hifi.aac"},
    # --- Folk / Roots / World ---
    {"id": "fipfolk",       "name": "FIP Monde",              "genre": "World folk & roots — Radio France",             "url": "https://icecast.radiofrance.fr/fipworld-hifi.aac"},
    {"id": "rpworld",       "name": "Radio Paradise World",   "genre": "World, folk & roots mix",                       "url": "https://stream.radioparadise.com/world-etc-192"},
    {"id": "radiomeuh",     "name": "Radio Meuh",             "genre": "Eclectic mountain radio — French Alps",         "url": "http://radiomeuh.ice.infomaniak.ch/radiomeuh-128.mp3"},
    {"id": "rfimusique",    "name": "RFI Musique",            "genre": "World music & culture — RFI, Paris",            "url": "http://live02.rfi.fr/rfimonde-96k.mp3"},
    # --- Reggae & Funk ---
    {"id": "fipreggae",     "name": "FIP Reggae",             "genre": "Reggae & dub — Radio France",                   "url": "https://icecast.radiofrance.fr/fipreggae-hifi.aac"},
    {"id": "fipgroove",     "name": "FIP Groove",             "genre": "Funk, soul & groove — Radio France",            "url": "https://icecast.radiofrance.fr/fipgroove-hifi.aac"},
    # --- European Independent ---
    {"id": "couleur3",      "name": "Couleur 3",             "genre": "Eclectic alternative — Swiss public radio",      "url": "https://stream.srg-ssr.ch/m/couleur3/mp3_128"},
    {"id": "bytefm",        "name": "ByteFM",                "genre": "Curated music radio — Hamburg, Germany",         "url": "https://bytefm.cast.addradio.de/bytefm/main/mid/stream"},
    {"id": "fluxfm",        "name": "FluxFM",                "genre": "Indie & eclectic — Berlin, Germany",             "url": "https://streams.fluxfm.de/live/mp3-320/"},
    {"id": "thelot",        "name": "The Lot Radio",          "genre": "Community rooftop radio — Brooklyn, NYC",       "url": "https://streams.radio.co/se1a320b47/listen"},
    # --- Discovery / Underground ---
    {"id": "dublab",        "name": "Dublab",                 "genre": "Experimental & underground — Los Angeles",      "url": "https://dublab.out.airtime.pro/dublab_a"},
    {"id": "resonancefm",   "name": "Resonance 104.4",        "genre": "Arts & experimental — London",                  "url": "https://stream.resonance.fm/resonance"},
    {"id": "cashmerefm",    "name": "Cashmere Radio",         "genre": "Underground & community — Berlin",              "url": "https://cashmereradio.out.airtime.pro/cashmereradio_a"},
    # --- Rock / Indie ---
    {"id": "rprock",        "name": "Radio Paradise Rock",    "genre": "Eclectic rock mix",                             "url": "http://stream.radioparadise.com/rock-192"},
    {"id": "fiprock",       "name": "FIP Rock",               "genre": "Rock & indie — Radio France",                   "url": "https://icecast.radiofrance.fr/fiprock-hifi.aac"},
    # --- Electronic ---
    {"id": "fipelectro",    "name": "FIP Electro",            "genre": "Electronic — Radio France",                     "url": "https://icecast.radiofrance.fr/fipelectro-hifi.aac"},
    {"id": "somadefcon",    "name": "SomaFM DEF CON",         "genre": "Hacker-themed electronica",                     "url": "https://ice2.somafm.com/defcon-128-mp3"},
    # --- Ambient / Mellow ---
    {"id": "rpmellow",      "name": "Radio Paradise Mellow",  "genre": "Acoustic & chill",                              "url": "http://stream.radioparadise.com/mellow-192"},
    {"id": "somagroove",    "name": "SomaFM Groove Salad",    "genre": "Ambient & downtempo",                           "url": "https://ice2.somafm.com/groovesalad-128-mp3"},
    {"id": "somadrone",     "name": "SomaFM Drone Zone",      "genre": "Atmospheric ambient",                           "url": "https://ice2.somafm.com/dronezone-128-mp3"},
    # --- Custom ---
    {"id": "custom",        "name": "Custom URL",             "genre": "Paste any stream URL",                          "url": ""},
]

FALLBACK_STREAMS = {
    "wkcr": ["http://wkcr.streamguys1.com/live"],
    "fip": ["http://direct.fipradio.fr/live/fip-midfi.mp3"],
}

# --- Shared playback state ---
_play_lock = threading.Lock()
_playing_station_id = None
_playing_station_name = None
_playing_device = None
_stop_grace_until = 0

# --- Chromecast cache ---
_cast_cache = {}
_cast_lock = threading.Lock()
_discovered = []

# --- Alarm state ---
_alarm_last_triggered_minute = None


def _load_config():
    """Load config from file with atomic read and defaults."""
    try:
        if os.path.exists(CONFIG_PATH):
            with open(CONFIG_PATH, "r") as f:
                return json.load(f)
    except Exception as e:
        LOG.error(f"Error loading config: {e}")

    return {
        "device_name": "Living Room",
        "station": "wkcr",
        "volume": 50,
        "alarm_enabled": False,
        "alarm_time": "07:00",
        "alarm_days": [1, 2, 3, 4, 5],  # Monday-Friday
        "alarm_station": "wkcr",
        "custom_url": "",
    }


def _save_config(cfg):
    """Save config to file with atomic write."""
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH) or ".", exist_ok=True)
        # Write to temp file first, then rename for atomicity
        temp_path = CONFIG_PATH + ".tmp"
        with open(temp_path, "w") as f:
            json.dump(cfg, f, indent=2)
        os.replace(temp_path, CONFIG_PATH)
        LOG.info("Config saved successfully")
    except Exception as e:
        LOG.error(f"Error saving config: {e}")


def _get_cast(name):
    """
    Three-phase cache pattern:
    1. Check cache (locked)
    2. Discover if not found (UNLOCKED)
    3. Store result (locked)
    """
    with _cast_lock:
        if name in _cast_cache:
            return _cast_cache[name]

    # Discover devices without lock
    try:
        chromecasts, browser = pychromecast.get_listed_chromecasts(
            friendly_names=[name], discovery_timeout=8
        )
        browser.stop_discovery()
        if chromecasts:
            cast = chromecasts[0]
            cast.wait()
            with _cast_lock:
                _cast_cache[cast.name] = cast
            return cast
    except Exception as e:
        LOG.error(f"Error discovering Chromecast '{name}': {e}")

    return None


def _find_station(station_id):
    """Find station in STATIONS by ID."""
    for station in STATIONS:
        if station["id"] == station_id:
            return station
    return None


def _guess_mime(url):
    """Guess MIME type from stream URL so Chromecast picks the right decoder fast."""
    u = url.lower()
    if u.endswith(".aac") or "/aac" in u or "-hifi.aac" in u:
        return "audio/aac"
    if u.endswith(".ogg") or "/ogg" in u:
        return "audio/ogg"
    if u.endswith(".flac") or "/flac" in u:
        return "audio/flac"
    if u.endswith(".m3u8"):
        return "application/x-mpegURL"
    # Default to mpeg for .mp3 and everything else
    return "audio/mpeg"


def play_station(station_id, device_name, vol, custom_url=""):
    """
    Play a station on a Chromecast device.
    Updates shared playback state.
    """
    global _playing_station_id, _playing_station_name, _playing_device, _stop_grace_until

    station = _find_station(station_id)
    if not station:
        LOG.error(f"Station '{station_id}' not found")
        return False

    stream_url = custom_url if custom_url and station_id == "custom" else station["url"]
    if not stream_url:
        LOG.error(f"No stream URL for station '{station_id}'")
        return False

    cast = _get_cast(device_name)
    if not cast:
        LOG.error(f"Chromecast device '{device_name}' not found")
        return False

    try:
        # Ensure cast is fully connected (may have gone stale since caching)
        cast.wait()
        mc = cast.media_controller

        # Normalize volume: ensure integer 0-100, convert to 0.0-1.0 for Chromecast
        if isinstance(vol, float) and vol <= 1.0:
            vol = int(vol * 100)  # Was stored as fraction, convert to percent
        vol = max(0, min(100, int(vol)))
        cast.set_volume(vol / 100.0)

        # Detect correct MIME type and tell Chromecast this is a LIVE stream
        mime = _guess_mime(stream_url)
        mc.play_media(stream_url, mime, stream_type="LIVE")

        # Update shared state
        with _play_lock:
            _playing_station_id = station_id
            _playing_station_name = station["name"]
            _playing_device = device_name
            _stop_grace_until = 0

        LOG.info(f"Now playing: {station['name']} on {device_name} at volume {vol}% (mime={mime})")
        return True
    except Exception as e:
        LOG.error(f"Error playing station: {e}")
        return False


def stop_playback(device_name):
    """
    Stop playback with grace period.
    Uses quit_app() + mc.stop() + grace period to prevent resurrection.
    """
    global _playing_station_id, _playing_station_name, _playing_device, _stop_grace_until

    cast = _get_cast(device_name)
    if not cast:
        LOG.warning(f"Chromecast device '{device_name}' not found for stop")
        with _play_lock:
            _playing_station_id = None
            _playing_station_name = None
            _playing_device = None
        return True

    try:
        cast.wait()
        mc = cast.media_controller

        # Triple-layer stop: quit_app, stop, grace period
        try:
            cast.quit_app()
            LOG.info(f"Quit app on {device_name}")
        except Exception as e:
            LOG.warning(f"Error quitting app: {e}")

        try:
            mc.stop()
            LOG.info(f"Stopped media on {device_name}")
        except Exception as e:
            LOG.warning(f"Error stopping media: {e}")

        # Update shared state with grace period
        with _play_lock:
            _playing_station_id = None
            _playing_station_name = None
            _playing_device = None
            _stop_grace_until = time.time() + STOP_GRACE_SECONDS

        return True
    except Exception as e:
        LOG.error(f"Error stopping playback: {e}")
        with _play_lock:
            _playing_station_id = None
            _playing_station_name = None
            _playing_device = None
        return False


def check_alarm():
    """
    Check if alarm should trigger.
    Runs every 30 seconds, checks time and day, prevents re-trigger within same minute.
    """
    global _alarm_last_triggered_minute

    cfg = _load_config()

    if not cfg.get("alarm_enabled"):
        return

    now = datetime.now()
    current_minute = (now.hour * 60) + now.minute
    current_day = now.weekday()  # 0=Monday, 6=Sunday

    alarm_time_str = cfg.get("alarm_time", "07:00")
    try:
        alarm_hour, alarm_minute = map(int, alarm_time_str.split(":"))
        alarm_minute_of_day = (alarm_hour * 60) + alarm_minute
    except:
        LOG.warning(f"Invalid alarm_time format: {alarm_time_str}")
        return

    alarm_days = cfg.get("alarm_days", [])

    # Check if it's time to trigger
    if (current_minute == alarm_minute_of_day and
        current_day in alarm_days and
        _alarm_last_triggered_minute != current_minute):

        _alarm_last_triggered_minute = current_minute

        device_name = cfg.get("device_name", "Living Room")
        alarm_station = cfg.get("alarm_station", cfg.get("station", "wkcr"))
        volume = cfg.get("volume", 50)

        LOG.info(f"Triggering alarm: {alarm_station} on {device_name}")
        play_station(alarm_station, device_name, volume)


def alarm_thread_worker():
    """Background thread that checks alarm every 30 seconds."""
    while True:
        try:
            check_alarm()
        except Exception as e:
            LOG.error(f"Error in alarm thread: {e}")
        time.sleep(30)


# --- Routes ---

@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint."""
    return jsonify({"ok": True, "status": "running", "devices": len(_discovered)})


@app.route("/volume-status", methods=["GET"])
def volume_status():
    """Read current volume from a Chromecast device."""
    device_name = request.args.get("device_name", "")
    if not device_name:
        return jsonify({"ok": False, "message": "Missing device_name"}), 400

    cast = _get_cast(device_name)
    if not cast:
        return jsonify({"ok": False, "message": f"Device '{device_name}' not found"}), 404

    try:
        cast.wait()
        vol = cast.status.volume_level  # 0.0 - 1.0
        return jsonify({"ok": True, "volume": vol, "device": device_name})
    except Exception as e:
        LOG.error(f"Error reading volume from {device_name}: {e}")
        return jsonify({"ok": False, "message": str(e)}), 500


@app.route("/")
def index():
    """Serve the UI."""
    ui_path = os.path.join(os.path.dirname(__file__), "ui.html")
    if os.path.exists(ui_path):
        return send_file(ui_path)
    return "<h1>Radio Alarm Clock</h1><p>UI file not found</p>", 404


@app.route("/config", methods=["GET"])
def get_config():
    """Return current config, stations list, and discovered devices."""
    cfg = _load_config()
    return jsonify({
        "config": cfg,
        "stations": STATIONS,
        "discovered": _discovered,
    })


@app.route("/config", methods=["POST"])
def set_config():
    """Save configuration."""
    try:
        data = request.get_json()
        cfg = _load_config()

        # Update allowed fields
        for key in ["device_name", "station", "volume", "alarm_enabled",
                    "alarm_time", "alarm_days", "alarm_station", "custom_url",
                    "favorites"]:
            if key in data:
                cfg[key] = data[key]

        _save_config(cfg)
        return jsonify({"status": "ok", "config": cfg})
    except Exception as e:
        LOG.error(f"Error setting config: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/favorite", methods=["POST"])
def toggle_favorite():
    """Toggle a station in the favorites list."""
    try:
        data = request.get_json()
        station_id = data.get("station_id")
        if not station_id:
            return jsonify({"status": "error", "message": "Missing station_id"}), 400

        cfg = _load_config()
        favorites = cfg.get("favorites", [])

        if station_id in favorites:
            favorites.remove(station_id)
            action = "removed"
        else:
            favorites.append(station_id)
            action = "added"

        cfg["favorites"] = favorites
        _save_config(cfg)
        return jsonify({"status": "ok", "action": action, "favorites": favorites})
    except Exception as e:
        LOG.error(f"Error toggling favorite: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/play", methods=["POST"])
def play():
    """Play a station."""
    try:
        data = request.get_json()
        station_id = data.get("station_id")
        device_name = data.get("device_name")
        volume = data.get("volume", 50)
        custom_url = data.get("custom_url", "")

        if not station_id or not device_name:
            return jsonify({"status": "error", "message": "Missing station_id or device_name"}), 400

        success = play_station(station_id, device_name, volume, custom_url)
        return jsonify({"status": "ok" if success else "error"})
    except Exception as e:
        LOG.error(f"Error in /play: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/stop", methods=["POST"])
def stop():
    """Stop playback."""
    try:
        data = request.get_json()
        device_name = data.get("device_name")

        if not device_name:
            return jsonify({"status": "error", "message": "Missing device_name"}), 400

        success = stop_playback(device_name)
        return jsonify({"status": "ok" if success else "error"})
    except Exception as e:
        LOG.error(f"Error in /stop: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/volume", methods=["POST"])
def set_volume():
    """Set volume on device."""
    try:
        data = request.get_json()
        device_name = data.get("device_name")
        volume = data.get("volume", 50)

        if not device_name:
            return jsonify({"status": "error", "message": "Missing device_name"}), 400

        cast = _get_cast(device_name)
        if not cast:
            return jsonify({"status": "error", "message": f"Device '{device_name}' not found"}), 400

        # Normalize volume
        if isinstance(volume, float) and volume <= 1.0:
            volume = int(volume * 100)
        volume = max(0, min(100, int(volume)))
        cast.set_volume(volume / 100.0)
        return jsonify({"status": "ok", "volume": volume})
    except Exception as e:
        LOG.error(f"Error setting volume: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route("/now-playing", methods=["GET"])
def now_playing():
    """Return what's currently playing."""
    with _play_lock:
        # Check if we're in grace period
        in_grace = time.time() < _stop_grace_until

        return jsonify({
            "station_id": _playing_station_id,
            "station_name": _playing_station_name,
            "device": _playing_device,
            "in_grace_period": in_grace,
        })


@app.route("/discover", methods=["GET"])
def discover():
    """Trigger mDNS discovery and return devices."""
    global _discovered

    try:
        LOG.info("Starting device discovery...")
        services, browser = pychromecast.discovery.discover_chromecasts(timeout=10)
        browser.stop_discovery()

        _discovered = []
        for svc in services:
            _discovered.append({
                "name": svc.friendly_name,
                "model": svc.model_name,
            })

        LOG.info(f"Discovered {len(_discovered)} devices")

        # Build cast objects and update cache
        if _discovered:
            chromecasts, _ = pychromecast.get_listed_chromecasts(
                friendly_names=[d["name"] for d in _discovered],
                discovery_timeout=5,
            )
            with _cast_lock:
                for cast in chromecasts:
                    _cast_cache[cast.name] = cast

        return jsonify({
            "status": "ok",
            "devices": _discovered,
        })
    except Exception as e:
        LOG.error(f"Error discovering devices: {e}")
        return jsonify({"status": "error", "message": str(e)}), 400


# --- Startup ---

def _startup_discovery():
    """Run discovery at startup so speakers are available immediately."""
    import time
    time.sleep(1)  # Let Flask finish starting
    global _discovered
    try:
        LOG.info("Startup discovery: scanning for Chromecast devices...")
        services, browser = pychromecast.discovery.discover_chromecasts(timeout=8)
        browser.stop_discovery()
        _discovered = []
        for svc in services:
            _discovered.append({"name": svc.friendly_name, "model": svc.model_name})
        LOG.info(f"Startup discovery: found {len(_discovered)} devices")
        if _discovered:
            chromecasts, _ = pychromecast.get_listed_chromecasts(
                friendly_names=[d["name"] for d in _discovered],
                discovery_timeout=5,
            )
            with _cast_lock:
                for cast in chromecasts:
                    _cast_cache[cast.name] = cast
    except Exception as e:
        LOG.error(f"Startup discovery error: {e}")


if __name__ == "__main__":
    # Start alarm checking thread
    alarm_thread = threading.Thread(target=alarm_thread_worker, daemon=True)
    alarm_thread.start()
    LOG.info("Alarm thread started")

    # Start background discovery
    disc_thread = threading.Thread(target=_startup_discovery, daemon=True)
    disc_thread.start()

    # Run Flask app
    app.run(host="0.0.0.0", port=8550, debug=False)
