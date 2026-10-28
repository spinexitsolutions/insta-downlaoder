"""One-time Instagram setup: logs in with a real browser and saves the account to .env.

After this the site logs in by itself (with a hidden browser) and logs in again
whenever Instagram expires the session, so you never copy a sessionid by hand.

    python login.py

Use a spare Instagram account.
"""

import getpass
import os
import sys

ENV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")


def save_to_env(values):
    lines = []
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, encoding="utf-8") as f:
            lines = [l.rstrip("\n") for l in f if l.split("=", 1)[0].strip() not in values]
    lines += [f"{k}={v}" for k, v in values.items()]
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def main():
    print("Instagram setup (use a spare account).")
    print("A Chrome window will open and log in by itself. If Instagram asks a security")
    print("question, answer it in that window.\n")
    username = input("Instagram username: ").strip().lstrip("@")
    password = getpass.getpass("Password (hidden while typing): ")

    os.environ["INSTAGRAM_USERNAME"] = username
    os.environ["INSTAGRAM_PASSWORD"] = password
    os.environ.pop("INSTAGRAM_SESSIONID", None)
    import extractor  # uses the same login code as the site

    loader = extractor._password_login(headless=False)
    if not loader:
        sys.exit("\nLogin failed (see the message above). Nothing was saved.")

    # The fresh browser session replaces any sessionid pasted by hand.
    save_to_env({"INSTAGRAM_USERNAME": username, "INSTAGRAM_PASSWORD": password, "INSTAGRAM_SESSIONID": ""})
    print(f"\nDone. Saved @{username} to {ENV_PATH}")
    print("Restart the site (Ctrl + C, then `python app.py`). From now on it logs in by itself.")


if __name__ == "__main__":
    main()
