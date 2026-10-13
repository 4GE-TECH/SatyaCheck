"""Create the shared admin account for the admin console (web3), once.

    python -m scripts.create_admin                       # admin@satyacheck.test
    python -m scripts.create_admin --email you@team.dev  # another address
    python -m scripts.create_admin --reset               # same account, new password

Needs in .env (Supabase -> Project Settings -> API):
    SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY (secret), SUPABASE_ANON_KEY (public)

What it does:
  1. creates an email + password user through Supabase's admin API, already confirmed
     (no email is sent), with a random 24-character password;
  2. writes the email, password and account id to admin-credentials.local.txt, which git
     ignores. Share that file with the team privately; the password is never printed;
  3. adds the account id to ADMIN_USER_IDS in .env (the server grants admin by id only);
  4. writes web3/.env.local with the public Supabase URL and anon key, so the console's
     sign-in works on the next `npm run dev` / build.

The backend must also run with AUTH_MODE=jwt for anyone to sign in; this script says so
rather than changing it, because dev mode is what the phone app uses locally.
"""

from __future__ import annotations

import argparse
import json
import secrets
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CREDENTIALS = ROOT / "admin-credentials.local.txt"
WEB_ENV = ROOT / "web3" / ".env.local"


def upsert_env(path: Path, key: str, value: str) -> None:
    """Set KEY=value in a .env-style file, replacing an existing line, keeping the rest."""
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    out, done = [], False
    for line in lines:
        if line.split("=", 1)[0].strip() == key:
            out.append(f"{key}={value}")
            done = True
        else:
            out.append(line)
    if not done:
        out.append(f"{key}={value}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def merge_ids(existing: str, new_id: str) -> str:
    ids = [x.strip() for x in existing.split(",") if x.strip()]
    return ",".join(ids + ([new_id] if new_id not in ids else []))


def _call(method: str, url: str, key: str, body: dict | None = None) -> tuple[int, dict]:
    # urllib uses the operating system's certificate store on Windows, which matters on
    # networks that re-sign HTTPS (certifi-based clients refuse those).
    req = urllib.request.Request(url, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"apikey": key, "Authorization": f"Bearer {key}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}


def _find_user(base: str, key: str, email: str):
    page = 1
    while True:
        status, data = _call("GET", f"{base}/auth/v1/admin/users?page={page}&per_page=200", key)
        if status != 200:
            return None
        users = data.get("users", [])
        for u in users:
            if (u.get("email") or "").lower() == email.lower():
                return u
        if len(users) < 200:
            return None
        page += 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--email", default="admin@satyacheck.test")
    ap.add_argument("--reset", action="store_true", help="the account exists: give it a new password")
    args = ap.parse_args()

    sys.path.insert(0, str(ROOT))
    import config

    env = config.read_dotenv(ROOT / ".env")
    base = (env.get("SUPABASE_URL") or "").rstrip("/")
    service = env.get("SUPABASE_SERVICE_ROLE_KEY") or ""
    anon = env.get("SUPABASE_ANON_KEY") or ""
    missing = [k for k, v in (("SUPABASE_URL", base), ("SUPABASE_SERVICE_ROLE_KEY", service),
                              ("SUPABASE_ANON_KEY", anon)) if not v]
    if missing:
        print(f"Add {', '.join(missing)} to .env first (Supabase -> Project Settings -> API).")
        return 1

    password = secrets.token_urlsafe(18)   # 24 characters
    existing = _find_user(base, service, args.email)
    if existing and not args.reset:
        print(f"{args.email} already exists (id {existing['id']}). Run with --reset to give it a new password.")
        return 1
    if existing:
        status, data = _call("PUT", f"{base}/auth/v1/admin/users/{existing['id']}", service,
                             {"password": password, "email_confirm": True})
        user = data if status == 200 else None
    else:
        status, data = _call("POST", f"{base}/auth/v1/admin/users", service,
                             {"email": args.email, "password": password, "email_confirm": True,
                              "app_metadata": {"satyacheck_role": "admin"}})
        user = data if status in (200, 201) else None
    if not user or not user.get("id"):
        print(f"Supabase refused ({status}): {data.get('msg') or data.get('message') or data.get('error_description') or data}")
        return 1

    user_id = user["id"]
    CREDENTIALS.write_text(
        "SatyaCheck admin console. Keep private; share only with the development team.\n"
        f"email: {args.email}\npassword: {password}\naccount id: {user_id}\n", encoding="utf-8")
    upsert_env(ROOT / ".env", "ADMIN_USER_IDS", merge_ids(env.get("ADMIN_USER_IDS", ""), user_id))
    upsert_env(WEB_ENV, "VITE_SUPABASE_URL", base)
    upsert_env(WEB_ENV, "VITE_SUPABASE_ANON_KEY", anon)

    print(f"Admin account {'reset' if existing else 'created'}: {args.email} (id {user_id}).")
    print(f"Credentials: {CREDENTIALS.name} (git-ignored; the password is not printed).")
    print("ADMIN_USER_IDS updated in .env; web3/.env.local written.")
    if (env.get("AUTH_MODE") or "dev").lower() != "jwt":
        print("Note: the backend runs AUTH_MODE=dev. Set AUTH_MODE=jwt in .env and restart it to sign in to the console.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
