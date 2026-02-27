"""
Validate Start/Stop Bot buttons against the running backend (no dev endpoints).
Uses DB + NEXTAUTH_SECRET to build a JWT for an existing user with API keys.
Requires: backend on API_BASE, ARQ worker, Redis, .env with NEXTAUTH_SECRET and DATABASE_URL.

Usage (from project root):
  python scripts/validate_bot_buttons_local.py
  EMAIL=your@email.com python scripts/validate_bot_buttons_local.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

try:
    import requests
except ImportError:
    print("pip install requests")
    sys.exit(1)

# Optional: PyJWT for local token (fallback if backend has no dev routes)
try:
    import jwt
except ImportError:
    jwt = None

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
EMAIL = os.getenv("EMAIL", "choiwangai@gmail.com")
WAIT_START = 30
POLL = 2


def main():
    from database import SessionLocal
    import models

    secret = os.getenv("NEXTAUTH_SECRET")
    if not secret:
        print("NEXTAUTH_SECRET not set. Set it in .env to run this validator.")
        return 1

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == EMAIL).first()
        if not user:
            print(f"User not found: {EMAIL}. Create the user and set API keys first.")
            return 1
        if not user.vault:
            print(f"User {EMAIL} has no API keys. Connect exchange first.")
            return 1
        user_id = user.id
    finally:
        db.close()

    token = jwt.encode(
        {"email": user.email, "sub": str(user.id)},
        secret,
        algorithm="HS256",
    )
    if hasattr(token, "decode"):
        token = token.decode("utf-8")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    pass_count = 0
    fail_count = 0

    def pass_(msg):
        nonlocal pass_count
        print(f"  [PASS] {msg}")
        pass_count += 1

    def fail(msg, detail=""):
        nonlocal fail_count
        print(f"  [FAIL] {msg} — {detail}")
        fail_count += 1

    print("--- Bot Buttons Validation (local JWT) ---")
    print(f"API_BASE={API_BASE}  EMAIL={EMAIL}  user_id={user_id}")

    print("1. Backend health")
    try:
        r = requests.get(f"{API_BASE}/openapi.json", timeout=5)
        if r.status_code == 200:
            pass_("Backend reachable")
        else:
            fail("Backend", f"status {r.status_code}")
            return 1
    except Exception as e:
        fail("Backend", str(e))
        return 1

    print("2. Start Bot")
    try:
        r = requests.post(f"{API_BASE}/start-bot", headers=headers, timeout=15)
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code == 200 and data.get("status") == "success":
            pass_("Start Bot success")
            if data.get("bot_status") in ("starting", "running"):
                pass_("Start response has bot_status")
        else:
            fail("Start Bot", f"status={r.status_code} body={r.text[:200]}")
    except Exception as e:
        fail("Start Bot", str(e))

    print("3. Poll until active")
    active = False
    for _ in range(WAIT_START // POLL):
        time.sleep(POLL)
        try:
            r = requests.get(f"{API_BASE}/bot-stats/{user_id}", headers=headers, timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data.get("active") is True:
                    pass_("Bot active")
                    active = True
                    break
        except Exception:
            pass
    if not active:
        fail("Bot active", "timeout (is ARQ worker running?)")

    print("4. Stop Bot")
    try:
        r = requests.post(f"{API_BASE}/stop-bot", headers=headers, timeout=15)
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code == 200 and data.get("status") == "success":
            pass_("Stop Bot success")
            if data.get("bot_status") == "stopped":
                pass_("Stop response has bot_status=stopped")
        else:
            fail("Stop Bot", f"status={r.status_code} body={r.text[:200]}")
    except Exception as e:
        fail("Stop Bot", str(e))
    time.sleep(3)
    try:
        r = requests.get(f"{API_BASE}/bot-stats/{user_id}", headers=headers, timeout=10)
        if r.status_code == 200 and r.json().get("active") is False:
            pass_("Bot stopped")
        else:
            fail("Stopped", "still active")
    except Exception as e:
        fail("Stopped", str(e))

    print("5. Start again")
    try:
        r = requests.post(f"{API_BASE}/start-bot", headers=headers, timeout=15)
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code == 200 and data.get("status") == "success":
            pass_("Start again success")
        else:
            fail("Start again", r.text[:200])
    except Exception as e:
        fail("Start again", str(e))

    print("6. Duplicate Start (idempotent)")
    try:
        r = requests.post(f"{API_BASE}/start-bot", headers=headers, timeout=15)
        data = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code == 200 and data.get("status") == "success":
            pass_("Duplicate Start success")
        else:
            fail("Duplicate Start", r.text[:200])
    except Exception as e:
        fail("Duplicate Start", str(e))

    print("7. Terminal logs")
    try:
        r = requests.get(f"{API_BASE}/terminal-logs/{user_id}", headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            if isinstance(data.get("lines"), list):
                pass_("terminal-logs OK")
            else:
                fail("Terminal logs", "no lines key")
        else:
            fail("Terminal logs", f"status {r.status_code}")
    except Exception as e:
        fail("Terminal logs", str(e))

    print("")
    print(f"--- Result: {pass_count} passed, {fail_count} failed ---")
    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
