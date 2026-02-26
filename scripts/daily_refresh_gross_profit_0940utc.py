"""
Standalone daily job: refresh gross profit from Bitfinex once per day at 09:40 UTC.
Gross profit is stored and updated only on the backend (user_profit_snapshot).

When the API server (uvicorn main:app) is running, the daily job runs automatically
at 09:40 UTC—no cron or Task Scheduler needed. Use this script only if you do not
run the API server (e.g. separate cron host).

Bitfinex limit: ~10 req/s per IP. Each user refresh does 3 ledger calls (USD, USDT, USDt).
We space users by DELAY_BETWEEN_USERS_SEC to stay under the limit and keep bot priority.

Cron (Linux/macOS), if not using the in-process scheduler:
  40 9 * * * cd /path/to/buildnew && python scripts/daily_refresh_gross_profit_0940utc.py

Windows Task Scheduler: create a daily task at 09:40 UTC only if the API is not running.

Env: CRON_SECRET (same as server), NEXT_PUBLIC_API_BASE (optional, default http://127.0.0.1:8000).
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
# Bitfinex ~10 req/s; each user = 3 ledger calls. Space users to avoid burst and leave headroom for bot.
DELAY_BETWEEN_USERS_SEC = 3.0


def main():
    if not CRON_SECRET:
        print("CRON_SECRET not set in .env. Skipping daily refresh.")
        return 0

    db = SessionLocal()
    try:
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
    print(f"Daily gross profit refresh at 09:40 UTC: {n} user(s), {DELAY_BETWEEN_USERS_SEC}s between calls")

    for i, uid in enumerate(user_ids):
        if i > 0:
            time.sleep(DELAY_BETWEEN_USERS_SEC)
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
