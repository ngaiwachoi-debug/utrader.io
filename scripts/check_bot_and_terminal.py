"""
Start the bot for a user by email, wait for the worker to produce logs, then verify
GET /terminal-logs/{user_id} returns lines. Requires backend and worker running.

Start by user_id requires auth. Set ADMIN_TOKEN (admin JWT) or NEXTAUTH_SECRET in env.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import requests
except ImportError:
    print("pip install requests")
    sys.exit(1)

try:
    import jwt as pyjwt
except ImportError:
    pyjwt = None

from database import SessionLocal
import models

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()
NEXTAUTH_SECRET = os.getenv("NEXTAUTH_SECRET", "").strip()
EMAIL = "choiwangai@gmail.com"
WAIT_SEC = 20
POLL_INTERVAL = 2


def _auth_headers_for_user(user):
    """Return headers with Authorization for start-bot/{user_id} or admin start."""
    if ADMIN_TOKEN:
        return {"Authorization": f"Bearer {ADMIN_TOKEN}", "Content-Type": "application/json"}
    if NEXTAUTH_SECRET and pyjwt:
        now = int(time.time())
        token = pyjwt.encode(
            {"email": user.email or "", "sub": str(user.id), "iat": now, "exp": now + 3600},
            NEXTAUTH_SECRET,
            algorithm="HS256",
        )
        if hasattr(token, "decode"):
            token = token.decode("utf-8")
        return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    return None


def main():
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == EMAIL).first()
        if not user:
            print(f"No user: {EMAIL}")
            return 1
        user_id = user.id
    finally:
        db.close()

    headers = _auth_headers_for_user(user)
    if not headers:
        print("Set ADMIN_TOKEN or NEXTAUTH_SECRET to start bot by user_id.")
        return 1

    print(f"User {EMAIL} -> user_id={user_id}")
    print(f"1. POST {API_BASE}/start-bot/{user_id} ...")
    try:
        url = f"{API_BASE}/admin/bot/start/{user_id}" if ADMIN_TOKEN else f"{API_BASE}/start-bot/{user_id}"
        r = requests.post(url, headers=headers, timeout=15)
    except requests.exceptions.RequestException as e:
        print(f"   Failed: {e}")
        return 1
    if r.status_code != 200:
        print(f"   Error {r.status_code}: {r.text[:200]}")
        return 1
    msg = (r.json() or {}).get("message", "")
    print(f"   OK – {msg}")

    print(f"2. Waiting up to {WAIT_SEC}s for worker to run and write logs ...")
    log_url = f"{API_BASE}/admin/bot/logs/{user_id}" if ADMIN_TOKEN else f"{API_BASE}/terminal-logs/{user_id}"
    for i in range(0, WAIT_SEC, POLL_INTERVAL):
        time.sleep(POLL_INTERVAL)
        try:
            r = requests.get(log_url, headers=headers, timeout=10)
        except requests.exceptions.RequestException as e:
            print(f"   GET terminal-logs failed: {e}")
            continue
        if r.status_code != 200:
            print(f"   GET terminal-logs {r.status_code}")
            continue
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        lines = data.get("lines") if isinstance(data, dict) else []
        if isinstance(lines, list) and len(lines) > 0:
            print(f"   Got {len(lines)} log line(s) after ~{i + POLL_INTERVAL}s.")
            print("   First line:", (lines[0][:80] + "..." if len(lines[0]) > 80 else lines[0]))
            print("3. Trading terminal API works.")
            return 0
    print("   No log lines yet. Is the ARQ worker running? (python scripts/run_worker.py)")
    print("3. Checking terminal-logs endpoint once more ...")
    try:
        r = requests.get(f"{API_BASE}/terminal-logs/{user_id}", timeout=10)
        data = r.json()
        lines = data.get("lines", [])
        print(f"   Response: {len(lines)} lines.")
        if lines:
            for i, line in enumerate(lines[:3]):
                print(f"   [{i}] {line[:70]}...")
    except Exception as e:
        print(f"   Error: {e}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
