"""Log in to Instagram once and save the session to .env.

Needed for story downloads (Instagram only shows stories to logged-in users)
and makes every other download less likely to be rate-limited.

    python login.py

Use a spare Instagram account, not your main one.
"""

import getpass
import os
import sys

import instaloader

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
    print("Instagram login for story downloads (use a spare account).\n")
    username = input("Instagram username: ").strip().lstrip("@")
    password = getpass.getpass("Password (hidden while typing): ")

    loader = instaloader.Instaloader(quiet=True)
    try:
        loader.login(username, password)
    except instaloader.exceptions.TwoFactorAuthRequiredException:
        code = input("Enter the 2FA code from your authenticator app / SMS: ").strip()
        try:
            loader.two_factor_login(code)
        except instaloader.exceptions.InstaloaderException as exc:
            sys.exit(f"\n2FA login failed: {exc}")
    except instaloader.exceptions.BadCredentialsException:
        sys.exit("\nWrong password.")
    except instaloader.exceptions.InstaloaderException as exc:
        sys.exit(
            f"\nLogin failed: {exc}\n\n"
            "Instagram may want you to confirm this login. Open the Instagram app, approve the\n"
            "'Was this you?' prompt and run this again. If it keeps failing, copy the sessionid\n"
            "cookie from your browser instead (see README, 'Instagram login')."
        )

    sessionid = loader.context._session.cookies.get_dict().get("sessionid")
    if not sessionid:
        sys.exit("\nLogged in, but Instagram didn't return a session. Try the browser method in README.")

    save_to_env({"INSTAGRAM_SESSIONID": sessionid, "INSTAGRAM_USERNAME": username})
    print(f"\nDone. Logged in as @{username} and saved the session to {ENV_PATH}")
    print("Restart the site (Ctrl + C, then `python app.py`) and stories will work.")


if __name__ == "__main__":
    main()
