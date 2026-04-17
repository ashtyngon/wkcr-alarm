# Sensory Radio

A beautiful radio player, in two flavors:

- **`/web`** — a public website anyone can open on any device. 51 curated HTTPS radio stations, sleep timer, favorites saved in your browser. Deploy it anywhere static files go.
- **`/` (root)** — a personal Raspberry Pi setup that casts radio to Google Home / Chromecast speakers on your local network, with a voice-controlled Google Home bridge and a wake-up alarm.

Same visual identity, two very different jobs.

---

## The web version — try it anywhere

A single HTML file plus a JSON list of stations. Nothing to install, nothing to configure.

```
cd web
python3 -m http.server 8081
# open http://localhost:8081
```

### What's in it

- **51 stations** across jazz, classical, opera, indie, world, electronic, FIP family, public radio
- **Search + mood filters** so you can find something fast
- **Sleep timer** (15m / 30m / 45m / 1h / 1.5h / 2h) that stops playback automatically
- **Favorites** saved to your browser — no login, no account
- **Works on phone, tablet, desktop** — the desktop layout centers itself as a phone-width column

### Deploy the web version

Works on any static host. Cloudflare Pages, Netlify, Vercel, GitHub Pages — all free.

**Cloudflare Pages** (recommended):
1. Push the repo to GitHub
2. Go to Cloudflare → Pages → Connect to Git → pick this repo
3. Set **Build output directory** to `web`
4. No build command needed (it's a static site)
5. Done. You get a free `*.pages.dev` URL plus optional custom domain.

**Vercel / Netlify**: same idea — point the output directory at `web/`.

**GitHub Pages**: move the contents of `web/` to a `docs/` folder or the repo root, enable Pages in repo settings.

### Why only 51 stations, not all 81?

The Pi-side version plays some international radio streams that are HTTP-only (Opera MRG, Aswat, Yerevan Nights, Egyptian Pop, etc.). Modern browsers refuse to play HTTP streams on HTTPS pages (mixed-content blocking), and static hosts force HTTPS. Rather than stand up a proxy, the web version just uses the 51 streams that already work over HTTPS directly.

If you want the niche HTTP streams on the web, you'd need to add a CORS/HTTPS proxy (a ~20-line Cloudflare Worker works). Happy to add that if anyone asks.

---

## The Raspberry Pi version — personal setup

This is what the author actually uses every day. It needs a specific setup: a Pi running 24/7 on the same Wi-Fi as Google Home / Chromecast speakers.

### What makes it different from the web version

- **Casts to your speakers** — audio plays on your Google Home Mini / Nest Hub / etc., not on your phone
- **Alarm clock** — wakes you up at a scheduled time on whichever speaker you pick
- **Voice control** via the Google Home app (through a Matter bridge running on the Pi)
- **Auto-reconnect** — keep-alive thread maintains Chromecast connections so switches are snappy

### Hardware you need

- Raspberry Pi 3 or newer, with Wi-Fi on your LAN
- At least one Google Home / Nest / Chromecast Audio device on the same Wi-Fi
- (Optional) A Nest Hub for Matter commissioning if you want voice control

### Setup

```bash
# On the Pi, over SSH:
git clone https://github.com/<you>/wkcr-alarm.git ~/wkcr-alarm
cd ~/wkcr-alarm
bash install.sh
```

`install.sh` creates a Python venv, installs `pychromecast` and `flask`, and registers a systemd service (`radio-alarm.service`) that starts Flask on port 8550 at boot.

Once running, open `http://<pi-ip>:8550` from any device on the same network.

### The Matter voice bridge (optional)

If you have a Google Home / Nest hub and want to say *"Hey Google, turn on Chechoo Jazz"*:

```bash
cd matter_bridge
bash setup.sh       # installs Node.js deps
node bridge.js      # start the bridge, prints a QR code for commissioning
```

Open the Google Home app → Add Device → Matter → scan the QR code. You'll get 6 virtual switches: `Chechoo Radio` (last-used station), `Chechoo Jazz`, `Chechoo French`, `Chechoo NPR`, `Chechoo Opera`, `Chechoo Techno`. Turning any of them on starts playback on your currently-selected speaker.

To run the Matter bridge automatically at boot, install the included systemd service:

```bash
sudo cp matter_bridge/chechoo-matter.service /etc/systemd/system/
sudo systemctl enable --now chechoo-matter
```

---

## Architecture

```
┌──────────────────┐         ┌────────────────────┐
│ Web version (/web)│────────▶│ Stream servers     │
│ HTML5 audio      │  HTTPS  │ (WNYC, FIP, etc.)  │
└──────────────────┘         └────────────────────┘
         Anyone, anywhere


┌──────────────────┐   HTTP   ┌──────────────┐  pychromecast  ┌────────────────┐
│ Browser          │─────────▶│ Flask on Pi  │────────────────▶│ Chromecast     │
│ ui.html          │          │ app.py :8550 │                 │ speaker        │
└──────────────────┘          └──────────────┘                 └────────────────┘
                                     ▲
                                     │
                              ┌──────┴──────┐
                              │ Matter      │  LAN  ┌─────────────────┐
                              │ bridge      │◀──────│ Google Home hub │
                              │ bridge.js   │       └─────────────────┘
                              │ :5540       │
                              └─────────────┘
         Your home network
```

## Project layout

```
├── app.py                    # Flask backend (Pi version)
├── ui.html                   # Full-featured Pi UI (alarm, speakers, voice)
├── config.json               # Runtime config (persisted settings)
├── install.sh                # Pi setup: venv + systemd service
├── matter_bridge/            # Node.js Matter bridge for voice control
│   ├── bridge.js
│   ├── package.json
│   ├── setup.sh
│   └── chechoo-matter.service
├── web/                      # Public web version
│   ├── index.html            # Standalone web player
│   └── stations.json         # Curated HTTPS-only station list
├── docs/                     # Design docs & plans
└── README.md
```

## Credits

Radio stations link directly to their publishers' public streams. No rights are claimed over any audio content; this is just a player, like a fancy `<audio>` tag.

UI built with Tailwind CSS (CDN), Space Grotesk + Manrope (Google Fonts), Material Symbols.
