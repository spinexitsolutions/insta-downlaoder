# ReelSaver – Instagram Downloader website

A light-theme Instagram downloader website, ready for Google AdSense. Paste a link and it downloads:

| Type | Example input |
|---|---|
| Reels, videos, IGTV | `instagram.com/reel/…`, `instagram.com/p/…`, `instagram.com/tv/…` |
| Photos | `instagram.com/p/…` |
| Carousels (multi-photo/video posts) | `instagram.com/p/…` (one download button per item) |
| Stories | `instagram.com/stories/username/…` (**needs an Instagram login**, see below) |
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

All settings are environment variables. Locally you can put them in a `.env` file next to `app.py`; see `.env.example`.

| Variable | What it does |
|---|---|
| `SITE_NAME` | Brand name shown everywhere (default `ReelSaver`) |
| `SITE_URL` | Your live domain, e.g. `https://www.yourdomain.com` (canonical URLs, sitemap) |
| `CONTACT_EMAIL` | Shown on Contact, Privacy, Terms and DMCA pages |
| `ADSENSE_CLIENT` | AdSense publisher id `ca-pub-…`. Turns on the AdSense script, the verification meta tag and `/ads.txt` |
| `ADSENSE_SLOT_TOP` / `_RESULT` / `_BOTTOM` | Optional ad unit ids for fixed ad positions. Without them, use Auto ads |
| `GA_MEASUREMENT_ID` | Optional Google Analytics 4 id |
| `INSTAGRAM_USERNAME` / `INSTAGRAM_PASSWORD` | Spare Instagram account the site logs in with (renews itself). Required for stories, strongly recommended on servers |
| `INSTAGRAM_SESSIONID` / `INSTAGRAM_COOKIES` | Alternatives: a browser `sessionid` cookie or a `cookies.txt` export |
| `RATE_LIMIT_PER_MINUTE` | Requests per IP per minute to `/api/info` (default 15) |

## Deploy (Render, easiest)

1. Push this repo to GitHub.
2. On https://render.com: **New → Blueprint**, pick the repo. It reads `render.yaml` and builds the `Dockerfile` (includes ffmpeg).
3. In the service's **Environment** tab set `SITE_URL`, `CONTACT_EMAIL` and later `ADSENSE_CLIENT`.
4. Add your domain under **Settings → Custom Domains** and point your DNS to it as Render shows.

Any host that runs Docker works the same (Railway, Fly.io, a VPS with `docker build -t reelsaver . && docker run -p 80:8000 --env-file .env reelsaver`). Without Docker: `gunicorn -w 2 --threads 4 -t 120 -b 0.0.0.0:$PORT app:app` (see `Procfile`).

## Instagram login (needed for stories)

Instagram only shows stories to logged-in users, and it rate-limits anonymous requests from servers. Give the site a **spare** Instagram account (not your main one) with **two-factor authentication turned off**. You set it up once; the site logs in by itself, saves the session, and logs in again automatically whenever Instagram expires it.

**Locally:** run

```bash
python login.py
```

It asks for the username and password, checks that the login works and saves them to `.env`. Restart the site.

**On a live host:** add these environment variables:

```
INSTAGRAM_USERNAME=your_spare_account
INSTAGRAM_PASSWORD=its_password
```

How it stays logged in:

- The first request logs in and saves the session to `.instagram_session` (path set by `INSTAGRAM_SESSION_FILE`). Restarts reuse it.
- If Instagram expires the session, the next request logs in again and retries. Login attempts are limited to one every 10 minutes so the account doesn't get flagged.
- If Instagram asks "Was this you?", approve it once in the Instagram app. The terminal prints a message whenever login fails.

Alternatives: `INSTAGRAM_SESSIONID` (the `sessionid` cookie copied from your browser) or `INSTAGRAM_COOKIES` (a `cookies.txt` export) also work, but they can't renew themselves. If you also set a password, the site falls back to it when they expire.

Keep the libraries updated: `pip install -U yt-dlp instaloader`.

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
