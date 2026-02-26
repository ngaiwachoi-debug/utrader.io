"""
Hourly job: refresh gross profit from Bitfinex for all users that have a vault.
Calls POST /api/cron/refresh-lending-stats per user with requests spread over the hour.

Setup:
  - Set CRON_SECRET in .env (same value as used by the server).
  - Run every hour via cron: 0 * * * * cd /path/to/buildnew && python scripts/hourly_refresh_gross_profit.py

Example (Windows Task Scheduler or cron):
  0 * * * * cd /path/to/buildnew && python scripts/hourly_refresh_gross_profit.py
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from database import SessionLocal
import models

try:
    import requests
except ImportError:
    print("Install requests: pip install requests")
    sys.exit(1)

API_BASE = os.getenv("NEXT_PUBLIC_API_BASE", "http://127.0.0.1:8000").rstrip("/")
CRON_SECRET = os.getenv("CRON_SECRET", "")


def main():
    if not CRON_SECRET:
        print("CRON_SECRET not set in .env. Skipping hourly refresh.")
        return 0

    db = SessionLocal()
    try:
        # All user IDs that have an API vault (Bitfinex keys)
        user_ids = [
            row[0]
            for row in db.query(models.User.id)
            .join(models.APIVault, models.User.id == models.APIVault.user_id)
            .distinct()
            .all()
        ]
    finally:
        db.close()

    if not user_ids:
        print("No users with vaults. Nothing to refresh.")
        return 0

    n = len(user_ids)
    stagger_sec = 3600.0 / max(n, 1)  # spread over one hour
    print(f"Refreshing gross profit for {n} user(s), ~{stagger_sec:.1f}s apart")

    for i, uid in enumerate(user_ids):
        if i > 0:
            time.sleep(stagger_sec)
        try:
            r = requests.post(
                f"{API_BASE}/api/cron/refresh-lending-stats",
                json={"user_id": uid},
                headers={"X-Cron-Secret": CRON_SECRET},
                timeout=120,
            )
            if r.ok:
                data = r.json()
                gross = data.get("gross_profit", 0)
                print(f"  user_id={uid} gross_profit={gross}")
            else:
                print(f"  user_id={uid} HTTP {r.status_code} {r.text[:200]}")
        except Exception as e:
            print(f"  user_id={uid} error: {e}")

    return 0


if __name__ == "__main__":
    sys.exit(0 if main() == 0 else 1)
