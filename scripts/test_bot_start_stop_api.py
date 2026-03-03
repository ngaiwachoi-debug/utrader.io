"""
Test start-bot and stop-bot API: success responses and 429 cooldown/rate-limit.
Requires: backend running (uvicorn) with latest code, .env with NEXTAUTH_SECRET and DATABASE_URL.
Usage: python scripts/test_bot_start_stop_api.py [user_id]
Default user_id=2.
After changing main.py, restart uvicorn so this test sees the new cooldown logic.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def main():
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"))

    user_id = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    from database import SessionLocal
    import models
    import jwt

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            print(f"User id={user_id} not found.")
            return 1
        email = (user.email or "").strip()
        if not email:
            print(f"User id={user_id} has no email.")
            return 1
    finally:
        db.close()

    secret = (os.getenv("NEXTAUTH_SECRET") or "").strip()
    if not secret:
        print("NEXTAUTH_SECRET not set in .env")
        return 1

    payload = {"sub": str(user_id), "email": email}
    token = jwt.encode(
        {**payload, "iat": int(time.time()), "exp": int(time.time()) + 3600},
        secret,
        algorithm="HS256",
    )
    if hasattr(token, "decode"):
        token = token.decode("utf-8")

    import urllib.request
    base = "http://127.0.0.1:8000"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    def post(path):
        req = urllib.request.Request(
            f"{base}{path}", data=b"", method="POST", headers=headers
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.getcode(), r.read().decode()
        except urllib.error.HTTPError as e:
            return e.code, e.read().decode()

    print(f"Testing bot start/stop for user_id={user_id} ({email})")
    print("-" * 50)

    # 1) Start bot -> 200
    code, body = post("/start-bot")
    print(f"POST /start-bot -> {code} {body[:120]}")
    if code != 200:
        print("Expected 200 on first start.")
        return 1

    # 2) Start again immediately -> 429 (start cooldown)
    code2, body2 = post("/start-bot")
    print(f"POST /start-bot (again) -> {code2} {body2[:120]}")
    if code2 != 429:
        print("Expected 429 (start cooldown) on immediate second start.")
        return 1

    # 3) Stop bot -> 200
    code3, body3 = post("/stop-bot")
    print(f"POST /stop-bot -> {code3} {body3[:120]}")
    if code3 != 200:
        print("Expected 200 on stop.")
        return 1

    # 4) Stop again immediately -> 429 (stop cooldown)
    code4, body4 = post("/stop-bot")
    print(f"POST /stop-bot (again) -> {code4} {body4[:120]}")
    if code4 != 429:
        print("Expected 429 (stop cooldown) on immediate second stop.")
        return 1

    print("-" * 50)
    print("All checks passed: start/stop and cooldown 429 work.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
