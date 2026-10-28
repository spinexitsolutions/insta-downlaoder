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
| `INSTAGRAM_SESSIONID` | Instagram login session (from `python login.py` or the browser). Required for stories, strongly recommended on servers |
| `INSTAGRAM_COOKIES` | Alternative to `INSTAGRAM_SESSIONID`: path to a `cookies.txt` export |
| `INSTAGRAM_USERNAME` | Username of that account |
| `RATE_LIMIT_PER_MINUTE` | Requests per IP per minute to `/api/info` (default 15) |

## Deploy (Render, easiest)

1. Push this repo to GitHub.
2. On https://render.com: **New → Blueprint**, pick the repo. It reads `render.yaml` and builds the `Dockerfile` (includes ffmpeg).
3. In the service's **Environment** tab set `SITE_URL`, `CONTACT_EMAIL` and later `ADSENSE_CLIENT`.
4. Add your domain under **Settings → Custom Domains** and point your DNS to it as Render shows.

Any host that runs Docker works the same (Railway, Fly.io, a VPS with `docker build -t reelsaver . && docker run -p 80:8000 --env-file .env reelsaver`). Without Docker: `gunicorn -w 2 --threads 4 -t 120 -b 0.0.0.0:$PORT app:app` (see `Procfile`).

## Instagram login (needed for stories)

Instagram only shows stories to logged-in users, and it rate-limits anonymous requests from servers. Give the site a login with a **spare** Instagram account (not your main one; it can get restricted).

**Option A: login script (easiest)**

```bash
python login.py
```

Enter the username and password (and 2FA code if asked). It saves `INSTAGRAM_SESSIONID` and `INSTAGRAM_USERNAME` to a `.env` file next to `app.py`. Restart the site.

**Option B: copy the sessionid from your browser** (use this if Instagram blocks the script login)

1. Log in to the spare account on instagram.com in Chrome.
2. Press F12 → **Application** → **Cookies** → `https://www.instagram.com`.
3. Copy the value of `sessionid`.
4. Create a `.env` file next to `app.py` with:
   ```
   INSTAGRAM_SESSIONID=paste_the_value_here
   INSTAGRAM_USERNAME=your_spare_account
   ```
5. Restart the site.

On a live host, add the same two values in the host's **Environment Variables** instead of a `.env` file. A full `cookies.txt` export also works via `INSTAGRAM_COOKIES=/path/to/cookies.txt`.

Sessions expire after a few weeks or if you log out. When stories stop working (the terminal prints "Instagram login expired"), log in again. Keep the libraries updated: `pip install -U yt-dlp instaloader`.

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
