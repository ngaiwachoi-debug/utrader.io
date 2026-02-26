"""
Start the lending bot for a user by email (e.g. choiwangai@gmail.com).
Requires: backend running (e.g. uvicorn main:app). Uses POST /start-bot/{user_id} (no auth).

Usage (from project root):
  python scripts/start_bot_for_email.py
  python scripts/start_bot_for_email.py choiwangai@gmail.com

Or with custom API base:
  API_BASE=http://127.0.0.1:8000 python scripts/start_bot_for_email.py choiwangai@gmail.com
"""
import os
import sys

# Project root = parent of scripts/
_script_dir = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_script_dir)
if _root not in sys.path:
    sys.path.insert(0, _root)

from database import SessionLocal
import models

try:
    import requests
except ImportError:
    print("Install requests: pip install requests")
    sys.exit(1)

DEFAULT_EMAIL = "choiwangai@gmail.com"
API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")


def main():
    email = (sys.argv[1] if len(sys.argv) > 1 else os.getenv("BOT_EMAIL", DEFAULT_EMAIL)).strip()
    if not email:
        print("Usage: python scripts/start_bot_for_email.py [email]")
        sys.exit(1)

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        if not user:
            print(f"No user found with email: {email}")
            sys.exit(1)
        if not user.vault:
            print(f"User {email} (id={user.id}) has no API keys. Connect exchange first.")
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
        print("Make sure the backend is running (e.g. uvicorn main:app).")
        sys.exit(1)

    try:
        body = r.json()
    except Exception:
        body = {}
    msg = body.get("message", r.text or f"HTTP {r.status_code}")

    if r.status_code == 200:
        print(f"OK: {msg}")
        print("If the worker is running (python scripts/run_worker.py), the bot will start within a few seconds.")
    else:
        print(f"Error ({r.status_code}): {msg}")
        sys.exit(1)


if __name__ == "__main__":
    main()
