"""Log in to Instagram with a real Chrome browser and return its cookies.

Instagram trusts a browser login far more than a scripted API login, so this
is how the site gets its session. The browser profile is kept on disk, so
Instagram sees the same "device" every time and asks fewer security questions.
"""

import os
import re
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
PROFILE_DIR = os.environ.get("INSTAGRAM_BROWSER_PROFILE") or os.path.join(HERE, ".browser_profile")
LOGIN_URL = "https://www.instagram.com/accounts/login/"
COOKIE_URL = "https://www.instagram.com"


def available():
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


def _launch(p, headless):
    return p.chromium.launch_persistent_context(
        PROFILE_DIR,
        headless=headless,
        # Optional: use an already installed Chrome/Chromium instead of Playwright's own.
        executable_path=os.environ.get("INSTAGRAM_BROWSER_PATH") or None,
        locale="en-US",
        viewport={"width": 1280, "height": 860},
        args=["--disable-blink-features=AutomationControlled", "--no-sandbox"],
    )


def _open_browser(p, headless):
    try:
        return _launch(p, headless)
    except Exception as exc:
        if "Executable doesn't exist" not in str(exc) and "playwright install" not in str(exc):
            raise
        # First run: download Chromium once, automatically.
        print("Downloading Chromium for Instagram login (one time, ~150 MB)...", flush=True)
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        return _launch(p, headless)


def _click_if_present(page, labels):
    for label in labels:
        try:
            button = page.get_by_role("button", name=label)
            if button.count():
                button.first.click(timeout=2000)
                return True
        except Exception:
            pass
    return False


# Instagram has used several login forms (its own, and Meta's shared one), so match any.
USERNAME_FIELDS = ('input[name="username"], input[name="email"], input[autocomplete*="username"], '
                   'input[aria-label*="username" i], input[aria-label*="email" i]')
PASSWORD_FIELDS = 'input[name="password"], input[name="pass"], input[type="password"]'
DEBUG_SCREENSHOT = os.path.join(HERE, "login_debug.png")


def _screenshot(page):
    try:
        page.screenshot(path=DEBUG_SCREENSHOT, full_page=True)
        print(f"Saved a screenshot of the Instagram page to {DEBUG_SCREENSHOT}", flush=True)
    except Exception:
        pass


def _fill_login_form(page, username, password):
    """Fill and submit the login form. Returns False if the form couldn't be found."""
    try:
        page.wait_for_selector(PASSWORD_FIELDS, state="visible", timeout=30000)
    except Exception:
        return False
    user_box = page.locator(USERNAME_FIELDS).locator("visible=true")
    if not user_box.count():
        # Fall back to the text box right before the password box.
        user_box = page.locator('input:not([type="password"]):not([type="hidden"])').locator("visible=true")
    if not user_box.count():
        return False
    user_box.first.fill(username)
    pass_box = page.locator(PASSWORD_FIELDS).locator("visible=true").first
    pass_box.fill(password)
    pass_box.press("Enter")
    # Meta's form has no real submit button, so Enter may do nothing: click "Log in".
    page.wait_for_timeout(2500)
    if page.locator(PASSWORD_FIELDS).locator("visible=true").count():
        for button in (page.get_by_role("button", name=re.compile(r"^\s*log ?in\s*$", re.I)),
                       page.locator('button[type="submit"]')):
            try:
                if button.count():
                    button.first.click(timeout=3000)
                    break
            except Exception:
                pass
    return True


def _cookies(ctx):
    return {c["name"]: c["value"] for c in ctx.cookies(COOKIE_URL)}


def login(username, password, headless=True, timeout=120, fresh=True):
    """Return Instagram cookies (with sessionid) or None if the login didn't finish.

    headless=False shows the window, so a person can solve a security check
    ("Was this you?", a code by email) if Instagram asks for one.
    """
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        ctx = _open_browser(p, headless)
        try:
            if fresh:
                ctx.clear_cookies()
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
            _click_if_present(page, ["Allow all cookies", "Only allow essential cookies", "Decline optional cookies"])

            if not _cookies(ctx).get("sessionid") and not _fill_login_form(page, username, password):
                _screenshot(page)
                if headless:
                    print(f"Couldn't find Instagram's login form (page: {page.url}).", flush=True)
                    return None
                print("Couldn't fill the login form automatically. Please log in yourself in the "
                      "browser window; this will continue as soon as you're logged in.", flush=True)

            deadline = time.time() + timeout
            warned = False
            while time.time() < deadline:
                cookies = _cookies(ctx)
                if cookies.get("sessionid"):
                    # Let Instagram finish setting the rest of its cookies.
                    _click_if_present(page, ["Save info", "Not now", "Not Now"])
                    page.wait_for_timeout(1500)
                    return _cookies(ctx)
                url = page.url
                if any(k in url for k in ("challenge", "two_factor", "checkpoint", "suspended")):
                    if headless:
                        print(f"Instagram wants a security check ({url}). Open the Instagram app "
                              "on your phone and tap 'This was me' (or approve the new login under "
                              "Settings > Accounts Center > Password and security > Where you're logged in). "
                              "The site tries again by itself in 10 minutes. Locally you can also run "
                              "`python login.py` to answer it in a window.", flush=True)
                        return None
                    if not warned:
                        print("Instagram is asking for a security check. Complete it in the "
                              "browser window...", flush=True)
                        warned = True
                if page.locator("#slfErrorAlert, [role=alert]").count():
                    message = page.locator("#slfErrorAlert, [role=alert]").first.inner_text()
                    if message.strip():
                        print(f"Instagram login error: {message.strip()}", flush=True)
                        return None
                page.wait_for_timeout(1000)
            _screenshot(page)
            print(f"Instagram login timed out (page: {page.url}).", flush=True)
            return None
        finally:
            ctx.close()
