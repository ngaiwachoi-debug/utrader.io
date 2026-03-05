"""
Test POST /api/bootstrap-user: create-or-get user from JWT and apply first-touch referral.

Flow:
  1. Build a JWT for a new Gmail address (no user in DB yet).
  2. Call POST /api/bootstrap-user with that JWT and referral_code = user 2's code.
  3. Assert response has id, referred_by == 2.

Requires: backend running, .env with NEXTAUTH_SECRET and DATABASE_URL.
  python scripts/test_bootstrap_user.py
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
    print("pip install pyjwt")
    sys.exit(1)

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
REFERRER_USER_ID = 2


def main():
    secret = (os.getenv("NEXTAUTH_SECRET") or "").strip()
    if not secret:
        print("NEXTAUTH_SECRET not set in .env")
        return 1

    from database import SessionLocal
    import models

    db = SessionLocal()
    try:
        referrer = db.query(models.User).filter(models.User.id == REFERRER_USER_ID).first()
        if not referrer or not referrer.referral_code:
            print(f"User {REFERRER_USER_ID} not found or has no referral_code")
            return 1
        ref_code = referrer.referral_code
    finally:
        db.close()

    # Use a unique email so we create a new user (first-touch)
    import time
    new_email = f"bootstrap.test.{int(time.time())}@gmail.com"

    token = jwt.encode(
        {"email": new_email, "sub": "bootstrap-test"},
        secret,
        algorithm="HS256",
    )
    if hasattr(token, "decode"):
        token = token.decode("utf-8")

    url = f"{API_BASE}/api/bootstrap-user"
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json={"referral_code": ref_code},
        timeout=10,
    )

    if resp.status_code != 200:
        print(f"FAIL: POST {url} → {resp.status_code} {resp.text[:300]}")
        return 1

    data = resp.json()
    user_id = data.get("id")
    referred_by = data.get("referred_by")
    email = data.get("email")

    if user_id is None or email != new_email:
        print(f"FAIL: unexpected response {data}")
        return 1

    if referred_by != REFERRER_USER_ID:
        print(f"FAIL: expected referred_by={REFERRER_USER_ID}, got referred_by={referred_by}")
        return 1

    print(f"PASS: user id={user_id} email={email} referred_by={referred_by}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
