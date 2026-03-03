"""
Test bot start/stop security (auth + same-user + rate limit) for user id 2.
Requires: backend running with latest code, .env with NEXTAUTH_SECRET and DATABASE_URL.

Restart the backend before running so the secured endpoints are active.
Run from project root:
  python scripts/test_bot_security_uid2.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

try:
    import requests
except ImportError:
    print("pip install requests")
    sys.exit(1)
try:
    import jwt
except ImportError:
    print("pip install PyJWT")
    sys.exit(1)

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
USER_ID = 2


def main():
    from database import SessionLocal
    import models

    secret = os.getenv("NEXTAUTH_SECRET")
    if not secret:
        print("NEXTAUTH_SECRET not set. Set it in .env")
        return 1

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.id == USER_ID).first()
        if not user:
            print(f"User id {USER_ID} not found in DB.")
            return 1
        email = user.email or ""
    finally:
        db.close()

    import time as _time
    now = int(_time.time())
    token = jwt.encode(
        {"email": email, "sub": str(user.id), "iat": now, "exp": now + 3600},
        secret,
        algorithm="HS256",
    )
    if hasattr(token, "decode"):
        token = token.decode("utf-8")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    passed = 0
    failed = 0

    def ok(msg):
        nonlocal passed
        print(f"  [PASS] {msg}")
        passed += 1

    def err(msg, detail=""):
        nonlocal failed
        print(f"  [FAIL] {msg} — {detail}")
        failed += 1

    print("--- Bot security tests (user_id=2) ---")
    print(f"API_BASE={API_BASE}  USER_ID={USER_ID}")

    # 1. Unauthenticated POST /start-bot/2 -> 401
    try:
        r = requests.post(f"{API_BASE}/start-bot/{USER_ID}", timeout=10)
        if r.status_code == 401:
            ok("POST /start-bot/2 without auth returns 401")
        else:
            err("POST /start-bot/2 without auth", f"expected 401 got {r.status_code}")
    except Exception as e:
        err("POST /start-bot/2 without auth", str(e))

    # 2. POST /start-bot/3 with user 2 JWT -> 403
    try:
        r = requests.post(f"{API_BASE}/start-bot/3", headers=headers, timeout=10)
        if r.status_code == 403:
            ok("POST /start-bot/3 as user 2 returns 403")
        else:
            err("POST /start-bot/3 as user 2", f"expected 403 got {r.status_code} {r.text[:150]}")
    except Exception as e:
        err("POST /start-bot/3 as user 2", str(e))

    # 3. POST /start-bot/2 with user 2 JWT -> 200 (or 400 if no tokens)
    try:
        r = requests.post(f"{API_BASE}/start-bot/{USER_ID}", headers=headers, timeout=15)
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code == 200 and data.get("status") == "success":
            ok("POST /start-bot/2 as user 2 returns 200 success")
        elif r.status_code == 400 and data.get("code") == "INSUFFICIENT_TOKENS":
            ok("POST /start-bot/2 as user 2 returns 400 INSUFFICIENT_TOKENS (expected if no tokens)")
        else:
            err("POST /start-bot/2 as user 2", f"status={r.status_code} body={r.text[:150]}")
    except Exception as e:
        err("POST /start-bot/2 as user 2", str(e))

    # 4. POST /stop-bot/2 with user 2 JWT -> 200
    try:
        r = requests.post(f"{API_BASE}/stop-bot/{USER_ID}", headers=headers, timeout=15)
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code == 200 and data.get("status") == "success":
            ok("POST /stop-bot/2 as user 2 returns 200 success")
        else:
            err("POST /stop-bot/2 as user 2", f"status={r.status_code} body={r.text[:150]}")
    except Exception as e:
        err("POST /stop-bot/2 as user 2", str(e))

    # 5. POST /start-bot (no path user_id) with user 2 JWT -> 200 or 400
    try:
        r = requests.post(f"{API_BASE}/start-bot", headers=headers, timeout=15)
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code == 200 and data.get("status") == "success":
            ok("POST /start-bot (me) as user 2 returns 200 success")
        elif r.status_code == 400 and data.get("code") == "INSUFFICIENT_TOKENS":
            ok("POST /start-bot (me) as user 2 returns 400 INSUFFICIENT_TOKENS")
        elif r.status_code == 429:
            ok("POST /start-bot (me) returns 429 rate limit (expected if >10/min)")
        else:
            err("POST /start-bot (me) as user 2", f"status={r.status_code} body={r.text[:150]}")
    except Exception as e:
        err("POST /start-bot (me) as user 2", str(e))

    print(f"\nResult: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
