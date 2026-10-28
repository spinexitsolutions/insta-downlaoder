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
| `INSTAGRAM_USERNAME` / `INSTAGRAM_PASSWORD` | Spare Instagram account the site logs in with, using a hidden browser (renews itself). Required for stories, strongly recommended on servers |
| `INSTAGRAM_SESSIONID` / `INSTAGRAM_COOKIES` | Alternatives: a browser `sessionid` cookie or a `cookies.txt` export |
| `RATE_LIMIT_PER_MINUTE` | Requests per IP per minute to `/api/info` (default 15) |

## Deploy (Render, easiest)

1. Push this repo to GitHub.
2. On https://render.com: **New → Blueprint**, pick the repo. It reads `render.yaml` and builds the `Dockerfile` (includes ffmpeg).
3. In the service's **Environment** tab set `SITE_URL`, `CONTACT_EMAIL` and later `ADSENSE_CLIENT`.
4. Add your domain under **Settings → Custom Domains** and point your DNS to it as Render shows.

Any host that runs Docker works the same (Railway, Fly.io, a VPS with `docker build -t reelsaver . && docker run -p 80:8000 --env-file .env reelsaver`). Without Docker: `gunicorn -w 1 --threads 16 -t 180 -b 0.0.0.0:$PORT app:app` (see `Procfile`).

## Instagram login (needed for stories)

Instagram only shows stories to logged-in users, and it distrusts logins made by scripts. So the site logs in the way a person does: it opens a real (hidden) Chrome browser with Playwright, signs in with a **spare** account, and keeps the session. When Instagram expires it, the site signs in again by itself. You never copy a `sessionid` by hand.

**One-time setup (locally):**

```bash
pip install -r requirements.txt
```

```bash
python login.py
```

Enter the spare account's username and password. A Chrome window opens and logs in on its own; if Instagram asks a security question ("Was this you?", a code by email), answer it in that window. The first run downloads Chromium automatically (~150 MB). Then restart the site.

**On a live host:** set these environment variables (the Docker image already includes Chromium):

```
INSTAGRAM_USERNAME=your_spare_account
INSTAGRAM_PASSWORD=its_password
```

How it stays logged in:

- The session from the browser login is saved to `.instagram_session` and reused after restarts. The browser profile is kept in `.browser_profile/`, so Instagram sees the same device each time.
- If Instagram expires the session, the next request logs in again with the hidden browser and retries. Login attempts are limited to one every 10 minutes so the account doesn't get flagged.
- If Instagram demands a security check during an automatic login, the terminal says so; run `python login.py` once to complete it in a visible window.
- Without Playwright the site falls back to instaloader's scripted login, which Instagram often rejects.

Optional: `INSTAGRAM_SESSIONID` (a `sessionid` cookie) or `INSTAGRAM_COOKIES` (a `cookies.txt` export) still work if you prefer to provide a session yourself. `INSTAGRAM_BROWSER_PATH` points to an existing Chrome/Chromium instead of Playwright's.

Check what Instagram answers at any time with `python check_instagram.py <username>`. Keep the libraries updated: `pip install -U yt-dlp instaloader playwright`.

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
