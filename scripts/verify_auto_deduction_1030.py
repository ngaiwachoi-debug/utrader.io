"""
Option 2: Integration test for 10:30 deduction path.
Uses a new DB session (like the scheduler), calls run_daily_token_deduction for user 2,
verifies one deduction and last_deduction_processed_date updated.

Prereq: Run scripts/reverse_today_set_yesterday_deducted.py so user 2 has
last_deduction_processed_date=yesterday and tokens not yet deducted for today.

Run from project root:
  python scripts/verify_auto_deduction_1030.py [user_id]
  Default user_id=2.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")


def main():
    user_id = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    import database
    import models
    from services.daily_token_deduction import run_daily_token_deduction, _utc_today

    today = _utc_today()
    db = database.SessionLocal()
    try:
        snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).first()
        bal = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).first()
        if not snap or not bal:
            print(f"User {user_id}: no snapshot or balance, skipping")
            return 1
        last_ded = getattr(snap, "last_deduction_processed_date", None)
        daily_gross = round(float(getattr(snap, "daily_gross_profit_usd", None) or 0), 2)
        tokens_before = round(float(bal.tokens_remaining or 0), 2)
        print(f"User {user_id} before: last_deduction_processed_date={last_ded}, daily_gross={daily_gross}, tokens_remaining={tokens_before}")

        log_entries, err = run_daily_token_deduction(db, user_ids=[user_id])
        if err:
            print(f"run_daily_token_deduction failed: {err}")
            return 1
        user_entries = [e for e in log_entries if e.get("user_id") == user_id]
        if daily_gross <= 0:
            if user_entries:
                print(f"FAIL: daily_gross<=0 but got {len(user_entries)} entries")
                return 1
            print("OK: daily_gross<=0, no deduction (expected)")
            return 0
        if last_ded == today:
            if user_entries:
                print(f"FAIL: already processed today but got {len(user_entries)} entries")
                return 1
            print("OK: already processed today, no deduction (expected)")
            return 0
        if len(user_entries) != 1:
            print(f"FAIL: expected 1 deduction entry for user {user_id}, got {len(user_entries)}")
            return 1
        e = user_entries[0]
        if e.get("tokens_deducted") != daily_gross:
            print(f"FAIL: tokens_deducted {e.get('tokens_deducted')} != daily_gross {daily_gross}")
            return 1
        snap2 = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).first()
        if getattr(snap2, "last_deduction_processed_date", None) != today:
            print(f"FAIL: last_deduction_processed_date not set to {today}")
            return 1
        print(f"OK: deducted {daily_gross}, after={e.get('tokens_remaining_after')}, last_deduction_processed_date={today}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
