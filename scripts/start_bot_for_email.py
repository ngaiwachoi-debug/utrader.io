"""
Start the lending bot for a user by email.
Requires: backend running (e.g. uvicorn main:app), Redis running, ARQ worker running.

Start/stop by user_id now requires auth. Use either:
  - ADMIN_TOKEN: admin JWT → calls POST /admin/bot/start/{user_id}
  - Or NEXTAUTH_SECRET: builds a JWT for that user → calls POST /start-bot/{user_id} (same-user)

Usage (from project root):
  ADMIN_TOKEN=<admin-jwt> python scripts/start_bot_for_email.py choiwangai@gmail.com
  # Or with NEXTAUTH_SECRET (builds user JWT):
  python scripts/start_bot_for_email.py choiwangai@gmail.com

  API_BASE=http://127.0.0.1:8000 python scripts/start_bot_for_email.py choiwangai@gmail.com
"""
import os
import sys
import time

# Add project root so we can import database and models
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import requests
except ImportError:
    print("Install requests: pip install requests")
    sys.exit(1)

from database import SessionLocal
import models

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "").strip()
NEXTAUTH_SECRET = os.getenv("NEXTAUTH_SECRET", "").strip()


def main():
    email = (sys.argv[1] if len(sys.argv) > 1 else "choiwangai@gmail.com").strip().lower()
    if not email or "@" not in email:
        print("Usage: python scripts/start_bot_for_email.py <email>")
        sys.exit(1)

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        if not user:
            print(f"No user found with email: {email}")
            sys.exit(1)
        user_id = user.id
    finally:
        db.close()

    headers = {"Content-Type": "application/json"}
    if ADMIN_TOKEN:
        url = f"{API_BASE}/admin/bot/start/{user_id}"
        headers["Authorization"] = f"Bearer {ADMIN_TOKEN}"
        print(f"Starting bot for {email} (user_id={user_id}) via admin endpoint ...")
    elif NEXTAUTH_SECRET:
        try:
            import jwt as pyjwt
            now = int(time.time())
            token = pyjwt.encode(
                {"email": user.email or "", "sub": str(user.id), "iat": now, "exp": now + 3600},
                NEXTAUTH_SECRET,
                algorithm="HS256",
            )
            if hasattr(token, "decode"):
                token = token.decode("utf-8")
            headers["Authorization"] = f"Bearer {token}"
        except Exception as e:
            print(f"JWT build failed: {e}. Set ADMIN_TOKEN or NEXTAUTH_SECRET.")
            sys.exit(1)
        url = f"{API_BASE}/start-bot/{user_id}"
        print(f"Starting bot for {email} (user_id={user_id}) via {url} ...")
    else:
        print("Set ADMIN_TOKEN (admin JWT) or NEXTAUTH_SECRET in env to start bot by user_id.")
        sys.exit(1)

    try:
        r = requests.post(url, headers=headers, timeout=15)
    except requests.exceptions.ConnectionError as e:
        print(f"Connection error: {e}")
        print("Ensure the backend is running (e.g. uvicorn main:app) and Redis is up.")
        sys.exit(1)

    if r.status_code == 200:
        data = r.json()
        print("Success:", data.get("message", data))
        print("Terminal output should appear within ~15 seconds (worker must be running).")
        return 0

    try:
        j = r.json()
        detail = j.get("detail", j) if isinstance(j, dict) else r.text
    except Exception:
        detail = r.text
    print(f"Error {r.status_code}: {detail}")
    if r.status_code == 401:
        print("Auth required: use ADMIN_TOKEN (admin JWT) or NEXTAUTH_SECRET to build user JWT.")
    if r.status_code == 403:
        print("Not authorized (admin required for admin endpoint, or same-user for /start-bot/{user_id}).")
    if r.status_code == 404:
        print("User may have no API keys saved. Save keys in Settings first.")
    if r.status_code == 402:
        print("Token balance too low or subscription expired. Add tokens or renew.")
    sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
