"""Diagnose story downloads: shows exactly what Instagram answers.

    python check_instagram.py maisamayhoon

Copy the whole output when asking for help. Passwords and session cookies are
never printed.
"""

import json
import sys

import app  # noqa: F401  (loads .env)
import extractor
import instaloader


def show(title, fn):
    print(f"\n=== {title}")
    try:
        result = fn()
        text = json.dumps(result, default=str) if not isinstance(result, str) else result
        print(text[:1500] + (" …(cut)" if len(text) > 1500 else ""))
        return result
    except Exception as exc:
        print(f"ERROR {type(exc).__name__}: {exc}")
        return None


def summarize_reels(data, uid):
    if not isinstance(data, dict):
        return data
    reel = (data.get("reels") or {}).get(uid) or next(
        (r for r in data.get("reels_media") or [] if str(r.get("id")) == uid), None)
    return {
        "status": data.get("status"),
        "top-level keys": list(data),
        "reels keys": list((data.get("reels") or {}))[:10],
        "reels_media count": len(data.get("reels_media") or []),
        "story items for this user": len((reel or {}).get("items") or []),
        "message": data.get("message"),
    }


def main():
    target = (sys.argv[1] if len(sys.argv) > 1 else input("Instagram username to check: ")).strip().lstrip("@")
    print(f"instaloader {instaloader.__version__}")
    print(f"Login configured: username={'yes' if extractor._username() else 'NO'}, "
          f"password={'yes' if extractor._password() else 'NO'}, "
          f"sessionid={'yes' if extractor._env_cookies() else 'no'}")

    with extractor._loader_lock:
        loader = extractor.get_loader()
    ctx = loader.context
    cookies = ctx._session.cookies.get_dict()
    print(f"Loader logged in: {ctx.is_logged_in} as {ctx.username!r}; "
          f"cookies present: {sorted(k for k in cookies if k in ('sessionid', 'ds_user_id', 'csrftoken', 'mid', 'ig_did'))}")

    show("Who does Instagram think we are? (web)",
         lambda: (extractor._web_api(loader, "api/v1/accounts/current_user/?edit=true").get("user") or {}).get("username"))

    profile = show(f"Profile @{target}", lambda: extractor._lookup_user(loader, target))
    if not profile:
        return
    uid = str(profile["id"])
    path = f"api/v1/feed/reels_media/?reel_ids={uid}"

    show("Stories via web api", lambda: summarize_reels(extractor._web_api(loader, path), uid))
    show("Stories via mobile api", lambda: summarize_reels(ctx.get_iphone_json(path, {}), uid))
    show("Stories tray (accounts with stories this login can see)", lambda: [
        (r.get("user") or {}).get("username") for r in
        (extractor._web_api(loader, "api/v1/feed/reels_tray/").get("tray") or [])][:30])
    show("Stories via instaloader (old method)", lambda: sum(
        s.itemcount for s in loader.get_stories(userids=[int(uid)])))


if __name__ == "__main__":
    main()
