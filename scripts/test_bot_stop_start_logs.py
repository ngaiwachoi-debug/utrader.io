"""
Stop bot for user, clear terminal logs, start again, wait, then read terminal_logs from Redis.
Use to verify worker runs and terminal shows TICKET ISSUED (no nonce: small).
Requires: ADMIN_TOKEN or NEXTAUTH_SECRET, backend + worker running, REDIS_URL in .env.
Usage: python scripts/test_bot_stop_start_logs.py [user_id] [wait_sec]
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except ImportError:
    pass

import requests

USER_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 2
WAIT_SEC = int(sys.argv[2]) if len(sys.argv) > 2 else 55
API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()
NEXTAUTH_SECRET = os.getenv("NEXTAUTH_SECRET", "").strip()


def _headers():
    if ADMIN_TOKEN:
        return {"Authorization": f"Bearer {ADMIN_TOKEN}", "Content-Type": "application/json"}
    if NEXTAUTH_SECRET:
        import jwt as pyjwt
        from database import SessionLocal
        import models
        db = SessionLocal()
        try:
            user = db.query(models.User).filter(models.User.id == USER_ID).first()
            if not user:
                return None
            now = int(time.time())
            token = pyjwt.encode(
                {"email": user.email or "", "sub": str(user.id), "iat": now, "exp": now + 3600},
                NEXTAUTH_SECRET,
                algorithm="HS256",
            )
            if hasattr(token, "decode"):
                token = token.decode("utf-8")
            return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        finally:
            db.close()
    return None


def main():
    headers = _headers()
    if not headers:
        print("Set ADMIN_TOKEN or NEXTAUTH_SECRET")
        return 1

    stop_url = f"{API_BASE}/admin/bot/stop/{USER_ID}" if ADMIN_TOKEN else f"{API_BASE}/stop-bot/{USER_ID}"
    start_url = f"{API_BASE}/admin/bot/start/{USER_ID}" if ADMIN_TOKEN else f"{API_BASE}/start-bot/{USER_ID}"

    print(f"1. POST {stop_url} ...")
    r = requests.post(stop_url, headers=headers, timeout=15)
    print(f"   {r.status_code}")
    time.sleep(4)

    # Clear terminal logs so we only see this run
    try:
        import redis
        rclient = redis.from_url(REDIS_URL)
        rclient.delete(f"terminal_logs:{USER_ID}")
        rclient.close()
        print("   Cleared terminal_logs for user.")
    except Exception as e:
        print(f"   (Could not clear Redis: {e})")

    print(f"2. POST {start_url} ...")
    r = requests.post(start_url, headers=headers, timeout=15)
    print(f"   {r.status_code} {r.json()}")
    print(f"3. Waiting {WAIT_SEC}s for worker and terminal logs...")
    time.sleep(WAIT_SEC)

    log_url = f"{API_BASE}/admin/bot/logs/{USER_ID}" if ADMIN_TOKEN else f"{API_BASE}/terminal-logs/{USER_ID}"
    print(f"4. GET {log_url} ...")
    r = requests.get(log_url, headers=headers, timeout=10)
    if r.status_code != 200:
        print(f"   {r.status_code}")
        return 1
    data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    lines = data.get("lines") or []
    print(f"   {len(lines)} lines")
    for line in lines[-40:]:
        try:
            print(f"   {line}")
        except UnicodeEncodeError:
            print(f"   {line.encode('ascii', errors='replace').decode('ascii')}")
    has_ticket = any("TICKET ISSUED" in str(l) for l in lines)
    has_nonce_small = any("nonce: small" in str(l) for l in lines)
    if has_ticket:
        print("\n   OK: TICKET ISSUED found in terminal log.")
    if has_nonce_small:
        print("\n   WARN: nonce: small still present (may be from overlapping job runs).")
    return 0 if has_ticket else 1


if __name__ == "__main__":
    sys.exit(main())
