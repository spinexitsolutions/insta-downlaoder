"""Turn an Instagram link (or @username) into a list of downloadable media.

Supported: posts (photo, video, carousel), Reels, IGTV, stories and profile
pictures. instaloader does the heavy lifting; yt-dlp and the public embed page
are fallbacks for posts when Instagram rate-limits instaloader.
"""

import html
import json
import os
import re
import threading
from http.cookiejar import MozillaCookieJar
from urllib.parse import urlparse

import instaloader
import requests
import yt_dlp

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)

USERNAME_RE = r"[A-Za-z0-9_.]{1,30}"
# Paths under instagram.com that look like usernames but aren't profiles.
RESERVED_PATHS = {
    "p", "reel", "reels", "tv", "stories", "explore", "accounts", "direct",
    "share", "about", "developer", "legal", "web", "api", "graphql", "s",
}


class ExtractError(Exception):
    """Error whose message is safe to show to the user."""


# ---------------------------------------------------------------- parsing

def parse_target(raw):
    """Return (kind, data) for user input, or raise ExtractError.

    kind is one of "post", "story", "profile", "share".
    """
    text = (raw or "").strip()
    if not text:
        raise ExtractError("Paste an Instagram link first.")

    if text.startswith("@") and re.fullmatch("@" + USERNAME_RE, text):
        return "profile", {"username": text[1:].lower()}

    if not re.match(r"^https?://", text, re.I):
        if re.match(r"^(www\.|m\.)?(instagram\.com|instagr\.am)/", text, re.I):
            text = "https://" + text
        elif re.fullmatch(USERNAME_RE, text) and not text.isdigit():
            return "profile", {"username": text.lower()}
        else:
            raise ExtractError("That doesn't look like an Instagram link.")

    parsed = urlparse(text)
    host = (parsed.hostname or "").lower()
    if host not in ("instagram.com", "www.instagram.com", "m.instagram.com", "instagr.am", "www.instagr.am"):
        raise ExtractError("Only instagram.com links are supported.")

    parts = [p for p in parsed.path.split("/") if p]
    if not parts:
        raise ExtractError("Paste a link to a post, Reel, story or profile.")

    # /share/... links redirect to the real post.
    if parts[0] == "share":
        return "share", {"url": text}

    # /p/CODE, /reel/CODE, /tv/CODE, optionally prefixed by /username/
    for i, part in enumerate(parts[:2]):
        if part in ("p", "reel", "reels", "tv") and len(parts) > i + 1:
            code = parts[i + 1]
            if re.fullmatch(r"[A-Za-z0-9_\-]{5,}", code):
                return "post", {"shortcode": code, "url": f"https://www.instagram.com/p/{code}/"}

    if parts[0] == "stories":
        if len(parts) >= 2 and parts[1] == "highlights":
            raise ExtractError("Highlights aren't supported yet. Open the story from the profile instead.")
        if len(parts) >= 2 and re.fullmatch(USERNAME_RE, parts[1]):
            story_id = parts[2] if len(parts) >= 3 and parts[2].isdigit() else None
            return "story", {"username": parts[1].lower(), "story_id": story_id}
        raise ExtractError("That story link looks incomplete.")

    if len(parts) == 1 and parts[0].lower() not in RESERVED_PATHS and re.fullmatch(USERNAME_RE, parts[0]):
        return "profile", {"username": parts[0].lower()}

    raise ExtractError("Paste a link to a post, Reel, story or profile.")


def resolve_share(url):
    """Follow an instagram.com/share/... redirect to the canonical URL."""
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15, allow_redirects=True)
        final = resp.url
        resp.close()
    except requests.RequestException:
        raise ExtractError("Couldn't open that share link. Try copying the link again.")
    kind, data = parse_target(final)
    if kind == "share":
        raise ExtractError("Couldn't open that share link. Try copying the link again.")
    return kind, data


# ---------------------------------------------------------------- instaloader

_loader = None
_loader_lock = threading.Lock()


def _load_cookies():
    path = os.environ.get("INSTAGRAM_COOKIES")
    if not path or not os.path.exists(path):
        return None
    jar = MozillaCookieJar(path)
    jar.load(ignore_discard=True, ignore_expires=True)
    cookies = {c.name: c.value for c in jar if "instagram.com" in c.domain}
    return cookies if cookies.get("sessionid") else None


def get_loader():
    global _loader
    if _loader is None:
        loader = instaloader.Instaloader(
            quiet=True,
            sleep=False,
            max_connection_attempts=1,
            request_timeout=20,
            download_video_thumbnails=False,
            save_metadata=False,
            user_agent=USER_AGENT,
        )
        cookies = _load_cookies()
        if cookies:
            loader.load_session(os.environ.get("INSTAGRAM_USERNAME", "session"), cookies)
        _loader = loader
    return _loader


def is_logged_in():
    return bool(_load_cookies())


def _item(kind, url, thumbnail=None, width=None, height=None, duration=None):
    return {"type": kind, "url": url, "thumbnail": thumbnail or (url if kind == "image" else None),
            "width": width, "height": height, "duration": duration}


def _post_via_instaloader(shortcode):
    with _loader_lock:
        loader = get_loader()
        post = instaloader.Post.from_shortcode(loader.context, shortcode)
        items = []
        if post.typename == "GraphSidecar":
            for node in post.get_sidecar_nodes():
                if node.is_video:
                    items.append(_item("video", node.video_url, node.display_url))
                else:
                    items.append(_item("image", node.display_url))
        elif post.is_video:
            items.append(_item("video", post.video_url, post.url, duration=post.video_duration))
        else:
            items.append(_item("image", post.url))
        return {
            "title": (post.caption or "").strip() or f"Post by @{post.owner_username}",
            "username": post.owner_username,
            "items": items,
        }


def _best_progressive(entry):
    """Highest-quality yt-dlp format that has video and audio in one file."""
    formats = entry.get("formats") or []
    # A missing codec means "unknown", not "absent": Instagram's plain
    # video_versions formats carry no codec info but include audio.
    progressive = [
        f for f in formats
        if f.get("url")
        and f.get("vcodec") != "none"
        and f.get("acodec") != "none"
        and (f.get("protocol") or "https").startswith("http")
    ]
    if progressive:
        return max(progressive, key=lambda f: (f.get("height") or 0, f.get("tbr") or 0))
    if not formats and entry.get("url"):
        return {"url": entry["url"], "height": entry.get("height"), "width": entry.get("width")}
    return None


def ydl_options(**extra):
    opts = {"quiet": True, "no_warnings": True, "http_headers": {"User-Agent": USER_AGENT}}
    cookie_file = os.environ.get("INSTAGRAM_COOKIES")
    if cookie_file and os.path.exists(cookie_file):
        opts["cookiefile"] = cookie_file
    opts.update(extra)
    return opts


def _post_via_ytdlp(url):
    with yt_dlp.YoutubeDL(ydl_options()) as ydl:
        info = ydl.sanitize_info(ydl.extract_info(url, download=False))
    entries = [e for e in (info.get("entries") or [info]) if e]
    items = []
    for index, entry in enumerate(entries):
        fmt = _best_progressive(entry)
        item = _item("video", fmt["url"] if fmt else None, entry.get("thumbnail"),
                     (fmt or {}).get("width"), (fmt or {}).get("height"), entry.get("duration"))
        if not fmt:
            # Only split video/audio streams: app merges them with yt-dlp on download.
            item["merge"] = {"url": url, "index": index}
        items.append(item)
    return {
        "title": info.get("title") or info.get("description") or "Instagram post",
        "username": info.get("uploader") or info.get("channel"),
        "items": items,
    }


def _post_via_embed(shortcode):
    """Photos from the public embed page, used when the API is rate-limited."""
    url = f"https://www.instagram.com/p/{shortcode}/embed/captioned/"
    resp = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=15)
    resp.raise_for_status()
    page = resp.text
    items = []

    # Newer embed pages carry the full media JSON (escaped) inside a script tag.
    match = re.search(r'\\"gql_data\\":(\{.*?\})\}\\"\}', page)
    if match:
        try:
            data = json.loads(match.group(1).replace('\\"', '"').replace("\\\\/", "/"))
            media = data.get("shortcode_media") or {}
            edges = (media.get("edge_sidecar_to_children") or {}).get("edges") or [{"node": media}]
            for edge in edges:
                node = edge.get("node") or {}
                if node.get("is_video") and node.get("video_url"):
                    items.append(_item("video", node["video_url"], node.get("display_url")))
                elif node.get("display_url"):
                    items.append(_item("image", node["display_url"]))
        except ValueError:
            items = []

    if not items:
        img = re.search(r'class="EmbeddedMediaImage"[^>]*src="([^"]+)"', page) or \
              re.search(r'<img[^>]+class="EmbeddedMediaImage"[^>]*>', page)
        if img and img.groups():
            items.append(_item("image", html.unescape(img.group(1))))

    if not items:
        raise ExtractError("No media found in this post.")
    user = re.search(r'class="UsernameText"[^>]*>([^<]+)<', page)
    return {"title": "Instagram post", "username": user.group(1) if user else None, "items": items}


def extract_post(shortcode, url):
    errors = []
    for attempt in (lambda: _post_via_instaloader(shortcode),
                    lambda: _post_via_ytdlp(url),
                    lambda: _post_via_embed(shortcode)):
        try:
            result = attempt()
            if result["items"]:
                return result
        except Exception as exc:  # each backend raises its own error types
            errors.append(exc)
    raise ExtractError(_friendly(errors))


def extract_profile(username):
    try:
        with _loader_lock:
            loader = get_loader()
            profile = instaloader.Profile.from_username(loader.context, username)
            pic = profile.get_profile_pic_url() if loader.context.is_logged_in else profile.profile_pic_url
            full_name = profile.full_name
    except instaloader.exceptions.ProfileNotExistsException:
        raise ExtractError(f"No Instagram account called @{username}.")
    except Exception as exc:
        raise ExtractError(_friendly([exc]))
    return {
        "title": full_name or f"@{username}",
        "username": username,
        "items": [_item("image", pic)],
        "note": "Profile picture",
    }


def extract_story(username, story_id=None):
    if not is_logged_in():
        raise ExtractError("Instagram only shows stories to logged-in users, and story downloads "
                           "aren't enabled on this site yet.")
    try:
        with _loader_lock:
            loader = get_loader()
            profile = instaloader.Profile.from_username(loader.context, username)
            items = []
            for story in loader.get_stories(userids=[profile.userid]):
                for s in story.get_items():
                    if story_id and str(s.mediaid) != story_id:
                        continue
                    if s.is_video:
                        items.append(_item("video", s.video_url, s.url))
                    else:
                        items.append(_item("image", s.url))
    except instaloader.exceptions.ProfileNotExistsException:
        raise ExtractError(f"No Instagram account called @{username}.")
    except Exception as exc:
        raise ExtractError(_friendly([exc]))
    if not items:
        raise ExtractError(f"@{username} has no active stories right now (or the account is private).")
    return {"title": f"@{username}'s story", "username": username, "items": items}


def extract(raw):
    kind, data = parse_target(raw)
    if kind == "share":
        kind, data = resolve_share(data["url"])
    if kind == "post":
        result = extract_post(data["shortcode"], data["url"])
    elif kind == "profile":
        result = extract_profile(data["username"])
    else:
        result = extract_story(data["username"], data.get("story_id"))
    result["kind"] = kind
    return result


def _friendly(errors):
    text = " ".join(str(e) for e in errors).lower()
    if "private" in text:
        return "This account is private. Only public posts can be downloaded."
    if "not found" in text or "404" in text or "does not exist" in text:
        return "This post wasn't found. It may have been deleted."
    if "login" in text or "401" in text or "429" in text or "wait a few minutes" in text or "rate" in text:
        return "Instagram is limiting requests right now. Please try again in a few minutes."
    return "Couldn't fetch this link. Check that it's public and try again."
