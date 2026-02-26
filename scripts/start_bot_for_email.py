"""
Start the lending bot for a user by email.
Requires: backend running (e.g. uvicorn main:app), Redis running, ARQ worker running.

Usage (from project root):
  python scripts/start_bot_for_email.py choiwangai@gmail.com

Or with custom API base:
  API_BASE=http://127.0.0.1:8000 python scripts/start_bot_for_email.py choiwangai@gmail.com
"""
import os
import sys

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

    url = f"{API_BASE}/start-bot/{user_id}"
    print(f"Starting bot for {email} (user_id={user_id}) via {url} ...")
    try:
        r = requests.post(url, timeout=15)
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
    if r.status_code == 404:
        print("User may have no API keys saved. Save keys in Settings first.")
    if r.status_code == 402:
        print("Token balance too low or subscription expired. Add tokens or renew.")
    sys.exit(1)


if __name__ == "__main__":
    sys.exit(main())
