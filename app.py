"""Insta Downloader - paste an Instagram link, get the video.

Uses yt-dlp to resolve the post, then streams the video back to the browser
as a file download.
"""

import os
import re
import shutil
import tempfile
import threading
import time
from urllib.parse import urlparse

import requests
from flask import Flask, Response, jsonify, render_template, request, send_file
import yt_dlp

app = Flask(__name__)

INSTAGRAM_URL_RE = re.compile(
    r"^https?://(www\.|m\.)?(instagram\.com|instagr\.am)/"
    r"([A-Za-z0-9_.]+/)?(p|reel|reels|tv|share)/[A-Za-z0-9_\-]+",
    re.IGNORECASE,
)

# Only these hosts may be proxied, so /api/download can't be abused to fetch
# arbitrary URLs from the server.
ALLOWED_MEDIA_HOST_SUFFIXES = (".cdninstagram.com", ".fbcdn.net")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)

CACHE_TTL_SECONDS = 600
_cache = {}
_cache_lock = threading.Lock()


def normalize_url(url):
    url = (url or "").strip()
    if url and not url.startswith(("http://", "https://")):
        url = "https://" + url
    return url


def is_instagram_url(url):
    return bool(INSTAGRAM_URL_RE.match(url))


def ydl_options(**extra):
    opts = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": False,
        "http_headers": {"User-Agent": USER_AGENT},
    }
    cookie_file = os.environ.get("INSTAGRAM_COOKIES")
    if cookie_file and os.path.exists(cookie_file):
        opts["cookiefile"] = cookie_file
    opts.update(extra)
    return opts


def extract_info(url):
    """Return yt-dlp info for a post, cached briefly so download doesn't re-fetch."""
    now = time.time()
    with _cache_lock:
        hit = _cache.get(url)
        if hit and now - hit[0] < CACHE_TTL_SECONDS:
            return hit[1]
    with yt_dlp.YoutubeDL(ydl_options()) as ydl:
        info = ydl.extract_info(url, download=False)
        info = ydl.sanitize_info(info)
    with _cache_lock:
        _cache[url] = (now, info)
        for key in [k for k, (t, _) in _cache.items() if now - t >= CACHE_TTL_SECONDS]:
            del _cache[key]
    return info


def media_entries(info):
    """Flatten a single post or a carousel into a list of entries."""
    if info.get("_type") == "playlist" or info.get("entries"):
        return [e for e in (info.get("entries") or []) if e]
    return [info]


def best_progressive_format(entry):
    """Highest-quality format that already has video and audio in one file."""
    formats = entry.get("formats") or []
    progressive = [
        f for f in formats
        # A missing codec means "unknown", not "absent": Instagram's plain
        # video_versions formats carry no codec info but include audio.
        if f.get("url")
        and f.get("vcodec") != "none"
        and f.get("acodec") != "none"
        and (f.get("protocol") or "https").startswith("http")
    ]
    if progressive:
        return max(progressive, key=lambda f: (f.get("height") or 0, f.get("tbr") or 0))
    # Instagram often returns a single top-level url with no formats list.
    if not formats and entry.get("url"):
        return {"url": entry["url"], "ext": entry.get("ext") or "mp4",
                "height": entry.get("height"), "width": entry.get("width")}
    return None


def is_allowed_media_url(url):
    host = (urlparse(url).hostname or "").lower()
    return any(host.endswith(suffix) for suffix in ALLOWED_MEDIA_HOST_SUFFIXES)


def safe_filename(name, ext):
    name = re.sub(r"[^A-Za-z0-9_\-]+", "_", name or "instagram").strip("_")[:60]
    return f"{name or 'instagram'}.{ext or 'mp4'}"


def friendly_error(exc):
    msg = str(exc)
    lowered = msg.lower()
    if "login" in lowered or "private" in lowered or "rate-limit" in lowered:
        return ("Instagram asked for a login for this post. It may be private, or the server is rate-limited. "
                "Try again later, or set INSTAGRAM_COOKIES (see README).")
    if "unsupported url" in lowered:
        return "This link is not supported. Paste an Instagram post or reel link."
    if "ffmpeg" in lowered:
        return "This video needs ffmpeg to download. Install ffmpeg and restart the app (see README)."
    if "no video" in lowered:
        return "No video found in this post."
    return "Could not fetch the video. Check the link and try again."


@app.get("/")
def index():
    return render_template("index.html")


@app.post("/api/info")
def api_info():
    data = request.get_json(silent=True) or {}
    url = normalize_url(data.get("url"))
    if not is_instagram_url(url):
        return jsonify(error="Paste a valid Instagram post, reel or IGTV link."), 400
    try:
        info = extract_info(url)
    except Exception as exc:  # yt-dlp raises many error types
        app.logger.warning("extract failed for %s: %s", url, exc)
        return jsonify(error=friendly_error(exc)), 422

    items = []
    for i, entry in enumerate(media_entries(info)):
        fmt = best_progressive_format(entry)
        has_split_streams = any(
            f.get("vcodec") != "none" for f in entry.get("formats") or []
        )
        if not fmt and not has_split_streams:
            continue
        items.append({
            "index": i,
            "thumbnail": entry.get("thumbnail"),
            "duration": entry.get("duration"),
            "width": (fmt or {}).get("width") or entry.get("width"),
            "height": (fmt or {}).get("height") or entry.get("height"),
        })

    if not items:
        return jsonify(error="No video found in this post."), 404

    return jsonify(
        title=info.get("title") or info.get("description") or "Instagram video",
        uploader=info.get("uploader") or info.get("channel"),
        items=items,
    )


@app.get("/api/download")
def api_download():
    url = normalize_url(request.args.get("url"))
    if not is_instagram_url(url):
        return jsonify(error="Invalid Instagram link."), 400
    try:
        index = int(request.args.get("index", 0))
        info = extract_info(url)
        entry = media_entries(info)[index]
    except (ValueError, IndexError):
        return jsonify(error="Video not found."), 404
    except Exception as exc:
        app.logger.warning("extract failed for %s: %s", url, exc)
        return jsonify(error=friendly_error(exc)), 422

    base = entry.get("uploader") or entry.get("id") or "instagram"
    fmt = best_progressive_format(entry)

    if fmt and is_allowed_media_url(fmt["url"]):
        return stream_remote(fmt["url"], safe_filename(f"{base}_{entry.get('id', '')}", fmt.get("ext")))

    # No single-file format: let yt-dlp download video+audio and merge (needs ffmpeg).
    return download_and_merge(url, index, safe_filename(f"{base}_{entry.get('id', '')}", "mp4"))


def stream_remote(media_url, filename):
    upstream = requests.get(
        media_url,
        stream=True,
        timeout=30,
        headers={"User-Agent": USER_AGENT, "Referer": "https://www.instagram.com/"},
    )
    if upstream.status_code != 200:
        upstream.close()
        return jsonify(error="Instagram refused the download. Please try again."), 502

    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": upstream.headers.get("Content-Type", "video/mp4"),
    }
    if upstream.headers.get("Content-Length"):
        headers["Content-Length"] = upstream.headers["Content-Length"]

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
    opts = ydl_options(
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
        return jsonify(error=friendly_error(exc)), 422


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
