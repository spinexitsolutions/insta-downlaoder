"""Instagram downloader website.

Paste a post, Reel, carousel, story or profile link and download the photos
and videos. Media is streamed through this server from Instagram's CDN.
"""

import os
import re
import shutil
import tempfile
import threading
import time
from collections import defaultdict, deque
from urllib.parse import urlencode, urlparse

import requests
import yt_dlp
from flask import Flask, Response, abort, jsonify, render_template, request, send_file


def load_dotenv(path=os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")):
    """Read KEY=VALUE lines from .env into the environment (real env vars win)."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, value = line.split("=", 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_dotenv()

import extractor  # noqa: E402  (reads settings loaded above)

app = Flask(__name__)

# Site settings, all overridable with environment variables so the same code
# runs locally and on the live domain.
SITE = {
    "name": os.environ.get("SITE_NAME", "ReelSaver"),
    "url": os.environ.get("SITE_URL", "").rstrip("/"),
    "email": os.environ.get("CONTACT_EMAIL", "contact@example.com"),
    # AdSense publisher id, e.g. "ca-pub-1234567890123456". Ads stay off until set.
    "adsense_client": os.environ.get("ADSENSE_CLIENT", "").strip(),
    "ad_slot_top": os.environ.get("ADSENSE_SLOT_TOP", "").strip(),
    "ad_slot_result": os.environ.get("ADSENSE_SLOT_RESULT", "").strip(),
    "ad_slot_bottom": os.environ.get("ADSENSE_SLOT_BOTTOM", "").strip(),
    "ga_id": os.environ.get("GA_MEASUREMENT_ID", "").strip(),
}

# Landing page per download type: slug -> copy. "" is the home page.
TOOLS = {
    "": {
        "tab": "Video",
        "h1": "Instagram Video Downloader",
        "title": "Instagram Downloader – Download Reels, Videos, Photos & Stories",
        "description": "Free Instagram downloader. Save Reels, videos, photos, carousels, stories and "
                       "profile pictures in HD. Paste the link, no login or app needed.",
        "lead": "Download Instagram videos, Reels, photos, carousels, stories and profile pictures in HD. Free, fast and no login.",
        "placeholder": "Paste Instagram link here",
    },
    "instagram-reels-downloader": {
        "tab": "Reels",
        "h1": "Instagram Reels Downloader",
        "title": "Instagram Reels Downloader – Save Reels in HD with Audio",
        "description": "Download Instagram Reels in HD with original audio. Paste the Reel link and save it as MP4.",
        "lead": "Save any public Instagram Reel as an HD MP4 with the original audio.",
        "placeholder": "Paste Reel link, e.g. instagram.com/reel/...",
    },
    "instagram-photo-downloader": {
        "tab": "Photo",
        "h1": "Instagram Photo Downloader",
        "title": "Instagram Photo Downloader – Save Instagram Pictures in Full Size",
        "description": "Download Instagram photos in full resolution. Paste the post link and save the picture as JPG.",
        "lead": "Download Instagram pictures in their original, full resolution.",
        "placeholder": "Paste photo post link, e.g. instagram.com/p/...",
    },
    "instagram-carousel-downloader": {
        "tab": "Carousel",
        "h1": "Instagram Carousel Downloader",
        "title": "Instagram Carousel Downloader – Download All Photos & Videos from a Post",
        "description": "Download every photo and video from an Instagram carousel (multi-image post) at once.",
        "lead": "Get every photo and video from a multi-image Instagram post in one go.",
        "placeholder": "Paste carousel post link",
    },
    "instagram-story-downloader": {
        "tab": "Story",
        "h1": "Instagram Story Downloader",
        "title": "Instagram Story Downloader – Save Stories Photos & Videos",
        "description": "Download Instagram stories (photos and videos) from public accounts. Paste the story link or username.",
        "lead": "Save photos and videos from public Instagram stories before they disappear.",
        "placeholder": "Paste story link, e.g. instagram.com/stories/username/...",
    },
    "instagram-profile-picture-downloader": {
        "tab": "Profile",
        "h1": "Instagram Profile Picture Downloader",
        "title": "Instagram Profile Picture Downloader – View & Save DP in Full Size",
        "description": "View and download any Instagram profile picture (DP) in full size. Enter a username or profile link.",
        "lead": "View and save any Instagram profile picture in full size. Enter a username or profile link.",
        "placeholder": "Enter username or profile link, e.g. @username",
    },
}

PAGES = {
    "about": ("about.html", "About Us"),
    "contact": ("contact.html", "Contact Us"),
    "privacy-policy": ("privacy.html", "Privacy Policy"),
    "terms": ("terms.html", "Terms of Use"),
    "dmca": ("dmca.html", "DMCA & Copyright"),
}

# Only these hosts may be proxied, so /api/media can't be abused to fetch
# arbitrary URLs from the server.
ALLOWED_MEDIA_HOST_SUFFIXES = (".cdninstagram.com", ".fbcdn.net")

CACHE_TTL_SECONDS = 600
_cache = {}
_cache_lock = threading.Lock()

RATE_LIMIT = int(os.environ.get("RATE_LIMIT_PER_MINUTE", "15"))
_hits = defaultdict(deque)
_hits_lock = threading.Lock()


@app.context_processor
def inject_site():
    base = SITE["url"] or request.url_root.rstrip("/")
    return {"site": SITE, "base_url": base, "year": time.gmtime().tm_year, "tools": TOOLS}


def client_ip():
    # Behind a host's proxy (Render, Railway, nginx) the real IP is the first forwarded one.
    forwarded = request.headers.get("X-Forwarded-For", "")
    return forwarded.split(",")[0].strip() or request.remote_addr or "?"


def rate_limited():
    now = time.time()
    with _hits_lock:
        q = _hits[client_ip()]
        while q and now - q[0] > 60:
            q.popleft()
        if len(q) >= RATE_LIMIT:
            return True
        q.append(now)
        if len(_hits) > 10000:
            for ip in [ip for ip, d in _hits.items() if not d or now - d[-1] > 60]:
                del _hits[ip]
    return False


def cached_extract(raw):
    key = raw.strip()
    now = time.time()
    with _cache_lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < CACHE_TTL_SECONDS:
            return hit[1]
    result = extractor.extract(key)
    with _cache_lock:
        _cache[key] = (now, result)
        for k in [k for k, (t, _) in _cache.items() if now - t >= CACHE_TTL_SECONDS]:
            del _cache[k]
    return result


def is_allowed_media_url(url):
    parsed = urlparse(url or "")
    host = (parsed.hostname or "").lower()
    return parsed.scheme == "https" and any(host.endswith(s) for s in ALLOWED_MEDIA_HOST_SUFFIXES)


def safe_name(name):
    return re.sub(r"[^A-Za-z0-9_\-]+", "_", name or "instagram").strip("_")[:60] or "instagram"


# ---------------------------------------------------------------- pages

@app.get("/")
def index():
    return render_template("index.html", tool=TOOLS[""], slug="")


@app.get("/<slug>")
def page(slug):
    if slug in TOOLS and slug:
        return render_template("index.html", tool=TOOLS[slug], slug=slug)
    if slug in PAGES:
        template, title = PAGES[slug]
        return render_template(template, title=title, slug=slug)
    abort(404)


@app.errorhandler(404)
def not_found(_):
    return render_template("404.html"), 404


@app.get("/ads.txt")
def ads_txt():
    client = SITE["adsense_client"]
    if not client:
        return Response("", mimetype="text/plain")
    pub = client.replace("ca-", "", 1)
    return Response(f"google.com, {pub}, DIRECT, f08c47fec0942fa0\n", mimetype="text/plain")


@app.get("/robots.txt")
def robots_txt():
    base = SITE["url"] or request.url_root.rstrip("/")
    body = f"User-agent: *\nDisallow: /api/\nAllow: /\n\nSitemap: {base}/sitemap.xml\n"
    return Response(body, mimetype="text/plain")


@app.get("/sitemap.xml")
def sitemap_xml():
    base = SITE["url"] or request.url_root.rstrip("/")
    paths = list(TOOLS) + list(PAGES)
    urls = "".join(f"<url><loc>{base}/{p}</loc></url>" for p in paths)
    body = ('<?xml version="1.0" encoding="UTF-8"?>'
            f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>')
    return Response(body, mimetype="application/xml")


# ---------------------------------------------------------------- API

@app.post("/api/info")
def api_info():
    if rate_limited():
        return jsonify(error="Too many requests. Please wait a minute and try again."), 429
    data = request.get_json(silent=True) or {}
    raw = (data.get("url") or "").strip()[:500]
    try:
        result = cached_extract(raw)
    except extractor.ExtractError as exc:
        return jsonify(error=str(exc)), 422
    except Exception:
        app.logger.exception("extract failed for %s", raw)
        return jsonify(error="Something went wrong. Please try again."), 500

    base = safe_name(f"{result.get('username') or 'instagram'}_{int(time.time())}")
    items = []
    for i, item in enumerate(result["items"]):
        ext = "mp4" if item["type"] == "video" else "jpg"
        name = f"{base}_{i + 1}.{ext}" if len(result["items"]) > 1 else f"{base}.{ext}"
        if item.get("url") and is_allowed_media_url(item["url"]):
            download = "/api/media?" + urlencode({"src": item["url"], "name": name, "dl": 1})
        elif item.get("merge"):
            download = "/api/download?" + urlencode({**item["merge"], "name": name})
        else:
            continue
        thumb = item.get("thumbnail")
        items.append({
            "type": item["type"],
            "thumbnail": "/api/media?" + urlencode({"src": thumb}) if is_allowed_media_url(thumb) else None,
            "download": download,
            "duration": item.get("duration"),
            "height": item.get("height"),
        })

    if not items:
        return jsonify(error="No downloadable media found in this link."), 404

    return jsonify(
        kind=result["kind"],
        title=(result.get("title") or "")[:200],
        username=result.get("username"),
        items=items,
    )


@app.get("/api/media")
def api_media():
    """Stream a photo or video from Instagram's CDN (inline preview or download)."""
    src = request.args.get("src", "")
    if not is_allowed_media_url(src):
        abort(400)
    filename = None
    if request.args.get("dl"):
        name = request.args.get("name", "")
        filename = safe_name(name.rsplit(".", 1)[0]) + (".mp4" if name.endswith(".mp4") else ".jpg")
    return stream_remote(src, filename)


@app.get("/api/download")
def api_download():
    """Download a video whose audio and video come as separate streams (merged by yt-dlp)."""
    url = request.args.get("url", "")
    try:
        kind, data = extractor.parse_target(url)
        index = int(request.args.get("index", 0))
    except (extractor.ExtractError, ValueError):
        abort(400)
    if kind != "post":
        abort(400)
    filename = safe_name(request.args.get("name", "").rsplit(".", 1)[0]) + ".mp4"
    return download_and_merge(data["url"], index, filename)


def stream_remote(media_url, filename=None):
    try:
        upstream = requests.get(
            media_url, stream=True, timeout=30,
            headers={"User-Agent": extractor.USER_AGENT, "Referer": "https://www.instagram.com/"},
        )
    except requests.RequestException:
        return jsonify(error="Couldn't reach Instagram. Please try again."), 502
    if upstream.status_code != 200:
        upstream.close()
        return jsonify(error="This link has expired. Paste the Instagram link again."), 502

    headers = {"Content-Type": upstream.headers.get("Content-Type", "application/octet-stream")}
    if upstream.headers.get("Content-Length"):
        headers["Content-Length"] = upstream.headers["Content-Length"]
    if filename:
        headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    else:
        headers["Cache-Control"] = "public, max-age=3600"

    def generate():
        try:
            for chunk in upstream.iter_content(chunk_size=64 * 1024):
                if chunk:
                    yield chunk
        finally:
            upstream.close()

    return Response(generate(), headers=headers)


def download_and_merge(url, index, filename):
    tmpdir = tempfile.mkdtemp(prefix="instadl_")
    # Merging separate video/audio streams needs ffmpeg; without it take the
    # best single file instead of failing.
    opts = extractor.ydl_options(
        format="bv*+ba/b" if shutil.which("ffmpeg") else "b",
        merge_output_format="mp4",
        outtmpl=os.path.join(tmpdir, "%(id)s.%(ext)s"),
        playlist_items=str(index + 1),
    )
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        files = [os.path.join(tmpdir, f) for f in os.listdir(tmpdir)]
        if not files:
            raise RuntimeError("no file produced")
        path = max(files, key=os.path.getsize)
        response = send_file(path, as_attachment=True, download_name=filename)
        response.call_on_close(lambda: shutil.rmtree(tmpdir, ignore_errors=True))
        return response
    except Exception as exc:
        shutil.rmtree(tmpdir, ignore_errors=True)
        app.logger.warning("download failed for %s: %s", url, exc)
        return jsonify(error="Couldn't download this video. Please try again."), 502


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
