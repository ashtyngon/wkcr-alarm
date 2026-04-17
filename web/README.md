# Sensory Radio — Web

Standalone static web app. Play internet radio in any modern browser.

## Run locally

```bash
python3 -m http.server 8081
# http://localhost:8081
```

## Deploy

Drop this folder onto any static host. See the root `../README.md` for Cloudflare Pages / Vercel / Netlify instructions.

## Files

- `index.html` — the whole app (HTML, CSS, JS, Tailwind via CDN)
- `stations.json` — curated HTTPS radio streams
- `_headers` — cache and security headers for Cloudflare Pages / Netlify
- `robots.txt` — allow indexing
