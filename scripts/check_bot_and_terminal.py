"""
Start the bot for a user by email, wait for the worker to produce logs, then verify
GET /terminal-logs/{user_id} returns lines. Requires backend and worker running.
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

from database import SessionLocal
import models

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
EMAIL = "choiwangai@gmail.com"
WAIT_SEC = 20
POLL_INTERVAL = 2


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

    print(f"User {EMAIL} -> user_id={user_id}")
    print(f"1. POST {API_BASE}/start-bot/{user_id} ...")
    try:
        r = requests.post(f"{API_BASE}/start-bot/{user_id}", timeout=15)
    except requests.exceptions.RequestException as e:
        print(f"   Failed: {e}")
        return 1
    if r.status_code != 200:
        print(f"   Error {r.status_code}: {r.text[:200]}")
        return 1
    msg = (r.json() or {}).get("message", "")
    print(f"   OK – {msg}")

    print(f"2. Waiting up to {WAIT_SEC}s for worker to run and write logs ...")
    for i in range(0, WAIT_SEC, POLL_INTERVAL):
        time.sleep(POLL_INTERVAL)
        try:
            r = requests.get(f"{API_BASE}/terminal-logs/{user_id}", timeout=10)
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
