"""
Standalone daily token deduction at 10:15 UTC.

When the API server (uvicorn main:app) is running, the deduction runs automatically
at 10:15 UTC. Use this script only if the API is not running (e.g. separate cron host).

Requires: user_profit_snapshot.daily_gross_profit_usd populated by the 09:40 UTC
gross profit refresh (same day).

Cron (Linux/macOS):
  15 10 * * * cd /path/to/buildnew && python scripts/daily_token_deduction_1015utc.py

Retries: 3 times with 5-minute intervals on failure. Set DEDUCTION_ALERT_WEBHOOK_URL
for Slack alert on final failure.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from database import SessionLocal
from services.daily_token_deduction import run_daily_token_deduction

DEDUCTION_RETRY_INTERVAL_SEC = 300
DEDUCTION_MAX_RETRIES = 3


def main():
    for attempt in range(1, DEDUCTION_MAX_RETRIES + 1):
        db = SessionLocal()
        try:
            log_entries, err = run_daily_token_deduction(db)
            if err:
                print(f"Attempt {attempt}/{DEDUCTION_MAX_RETRIES} failed: {err}", file=sys.stderr)
                if attempt < DEDUCTION_MAX_RETRIES:
                    time.sleep(DEDUCTION_RETRY_INTERVAL_SEC)
                continue
            for entry in log_entries:
                print(
                    f"user_id={entry['user_id']} gross_profit={entry['gross_profit']} "
                    f"tokens_deducted={entry['tokens_deducted']} new_tokens_remaining={entry['tokens_remaining_after']}"
                )
            if not log_entries:
                print("No users to deduct.")
            return 0
        except Exception as e:
            print(f"Attempt {attempt}/{DEDUCTION_MAX_RETRIES} error: {e}", file=sys.stderr)
            if attempt < DEDUCTION_MAX_RETRIES:
                time.sleep(DEDUCTION_RETRY_INTERVAL_SEC)
        finally:
            db.close()
    print("All retries failed.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
