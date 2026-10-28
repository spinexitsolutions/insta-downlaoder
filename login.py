"""One-time Instagram setup: saves the account to .env and checks that it works.

After this the site logs in by itself and logs in again whenever Instagram
expires the session, so you don't have to repeat this.

    python login.py

Use a spare Instagram account with two-factor authentication turned off.
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
    print("Instagram setup for story downloads (use a spare account with 2FA turned off).\n")
    username = input("Instagram username: ").strip().lstrip("@")
    password = getpass.getpass("Password (hidden while typing): ")

    os.environ["INSTAGRAM_USERNAME"] = username
    os.environ["INSTAGRAM_PASSWORD"] = password
    import extractor  # uses the same login code as the site

    try:
        os.remove(extractor.SESSION_FILE)
    except OSError:
        pass
    loader = extractor._password_login()
    if not loader:
        sys.exit("\nLogin failed (see the message above). Nothing was saved.")

    save_to_env({"INSTAGRAM_USERNAME": username, "INSTAGRAM_PASSWORD": password})
    print(f"\nDone. Saved @{username} to {ENV_PATH}")
    print("Restart the site (Ctrl + C, then `python app.py`). It will stay logged in by itself.")


if __name__ == "__main__":
    main()
