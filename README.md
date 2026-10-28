# ReelSaver – Instagram Downloader website

A light-theme Instagram downloader website, ready for Google AdSense. Paste a link and it downloads:

| Type | Example input |
|---|---|
| Reels, videos, IGTV | `instagram.com/reel/…`, `instagram.com/p/…`, `instagram.com/tv/…` |
| Photos | `instagram.com/p/…` |
| Carousels (multi-photo/video posts) | `instagram.com/p/…` (one download button per item) |
| Stories | `instagram.com/stories/username/…` (**needs server cookies**, see below) |
| Profile pictures | `@username` or `instagram.com/username` |
| Share links | `instagram.com/share/…` |

Pages included: home plus SEO landing pages for each type (`/instagram-reels-downloader`, `/instagram-photo-downloader`, `/instagram-carousel-downloader`, `/instagram-story-downloader`, `/instagram-profile-picture-downloader`), About, Contact, Privacy Policy (with the Google AdSense cookie disclosure), Terms, DMCA, a 404 page, `robots.txt`, `sitemap.xml` and `ads.txt`.

## Run locally

```bash
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000.

## Settings (environment variables)

All settings live in environment variables; see `.env.example`.

| Variable | What it does |
|---|---|
| `SITE_NAME` | Brand name shown everywhere (default `ReelSaver`) |
| `SITE_URL` | Your live domain, e.g. `https://www.yourdomain.com` (canonical URLs, sitemap) |
| `CONTACT_EMAIL` | Shown on Contact, Privacy, Terms and DMCA pages |
| `ADSENSE_CLIENT` | AdSense publisher id `ca-pub-…`. Turns on the AdSense script, the verification meta tag and `/ads.txt` |
| `ADSENSE_SLOT_TOP` / `_RESULT` / `_BOTTOM` | Optional ad unit ids for fixed ad positions. Without them, use Auto ads |
| `GA_MEASUREMENT_ID` | Optional Google Analytics 4 id |
| `INSTAGRAM_COOKIES` | Path to a `cookies.txt` of an Instagram account. Required for stories, strongly recommended on servers |
| `INSTAGRAM_USERNAME` | Username of that account |
| `RATE_LIMIT_PER_MINUTE` | Requests per IP per minute to `/api/info` (default 15) |

## Deploy (Render, easiest)

1. Push this repo to GitHub.
2. On https://render.com: **New → Blueprint**, pick the repo. It reads `render.yaml` and builds the `Dockerfile` (includes ffmpeg).
3. In the service's **Environment** tab set `SITE_URL`, `CONTACT_EMAIL` and later `ADSENSE_CLIENT`.
4. Add your domain under **Settings → Custom Domains** and point your DNS to it as Render shows.

Any host that runs Docker works the same (Railway, Fly.io, a VPS with `docker build -t reelsaver . && docker run -p 80:8000 --env-file .env reelsaver`). Without Docker: `gunicorn -w 2 --threads 4 -t 120 -b 0.0.0.0:$PORT app:app` (see `Procfile`).

## Instagram cookies (important on a server)

Instagram blocks or rate-limits requests from data-centre IPs, and only shows stories to logged-in users. To make the site reliable:

1. Create a **spare** Instagram account (don't use your main one; it can get restricted).
2. Log in to it in Chrome and export cookies with a "Get cookies.txt LOCALLY" type extension (Netscape format).
3. Upload the file to your host as a secret file (on Render: **Environment → Secret Files**, name `cookies.txt`, which lands at `/etc/secrets/cookies.txt`).
4. Set `INSTAGRAM_COOKIES=/etc/secrets/cookies.txt` and `INSTAGRAM_USERNAME=<that account>`.

Cookies expire every few weeks/months; re-export when downloads start failing. Keep `yt-dlp` and `instaloader` updated: `pip install -U yt-dlp instaloader`.

## AdSense checklist

1. Site live on your own domain with HTTPS. AdSense doesn't accept `*.onrender.com`-style subdomains.
2. Set `SITE_URL` and `CONTACT_EMAIL` to real values.
3. Apply at https://adsense.google.com with your domain. Set `ADSENSE_CLIENT` to the `ca-pub-…` id it gives you and redeploy. The verification code and `ads.txt` are then served automatically.
4. In AdSense enable **Auto ads**, or create display ad units and put their ids in `ADSENSE_SLOT_*`.
5. Set up the consent message for EEA/UK users under **Privacy & messaging** in AdSense.

## How it works

- `extractor.py` parses the link and fetches media: instaloader first, then yt-dlp (videos) and the public embed page (photos) as fallbacks.
- `POST /api/info` returns the media list; `GET /api/media` streams a photo or video from Instagram's CDN (only `*.cdninstagram.com` / `*.fbcdn.net` are allowed); `GET /api/download` merges split video/audio with yt-dlp + ffmpeg.

Download only content you have the right to use.
