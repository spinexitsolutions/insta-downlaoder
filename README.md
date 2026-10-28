# Insta Downloader

Paste an Instagram reel / post / IGTV link and download the video. Carousel posts with several videos show one download button per video.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000, paste a link (it starts on paste) and press **Download video**.

For production use gunicorn:

```bash
gunicorn -w 2 -b 0.0.0.0:5000 app:app
```

`ffmpeg` is optional; it's only needed when Instagram serves video and audio as separate streams.

## How it works

- `POST /api/info` takes `{"url": "..."}`, uses [yt-dlp](https://github.com/yt-dlp/yt-dlp) to read the post and returns the videos it found.
- `GET /api/download?url=...&index=0` streams the video back as an `.mp4` attachment. It only proxies Instagram CDN hosts (`*.cdninstagram.com`, `*.fbcdn.net`).

## Login-required / rate-limited posts

Only public posts work without login. If Instagram starts asking for a login (common on cloud servers), export your Instagram cookies to a Netscape-format `cookies.txt` and run:

```bash
INSTAGRAM_COOKIES=/path/to/cookies.txt python app.py
```

Keep `yt-dlp` updated (`pip install -U yt-dlp`): Instagram changes often and yt-dlp releases fixes quickly.

Download only content you have the right to use.
