"""
After rolling back user 2 for today: set snapshot daily_gross=4.41 (today), run run_daily_token_deduction,
verify tokens_remaining decreased by 4.41 and last_gross_usd_used = 4.41.

  python scripts/rollback_uid2_two_days.py   # first
  python scripts/run_auto_deduction_test_uid2.py
"""
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")


def main():
    user_id = 2
    expected_daily_gross = 4.41

    import database
    import models
    from services import token_ledger_service as token_ledger_svc
    from services.daily_token_deduction import run_daily_token_deduction

    db = database.SessionLocal()
    try:
        before = token_ledger_svc.get_tokens_remaining(db, user_id)
        snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).first()
        if not snap:
            print("No user_profit_snapshot for user 2")
            return 1

        today_utc = datetime.utcnow().date()
        snap.daily_gross_profit_usd = expected_daily_gross
        if hasattr(snap, "last_daily_snapshot_date"):
            snap.last_daily_snapshot_date = today_utc
        if hasattr(snap, "last_deduction_processed_date"):
            snap.last_deduction_processed_date = None
        db.commit()
        db.expire_all()
        print(f"Set snapshot: daily_gross_profit_usd={expected_daily_gross}, last_daily_snapshot_date={today_utc}")

        log_entries, err = run_daily_token_deduction(db, user_ids=[user_id])
        if err:
            print(f"run_daily_token_deduction failed: {err}")
            return 1

        user2_entries = [e for e in log_entries if e.get("user_id") == user_id]
        after = token_ledger_svc.get_tokens_remaining(db, user_id)
        tb = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).first()
        last_gross = float(tb.last_gross_usd_used or 0) if tb else 0

        print(f"Deductions for user 2: {len(user2_entries)}")
        for e in user2_entries:
            print(f"  tokens_deducted={e.get('tokens_deducted')} after={e.get('tokens_remaining_after')}")
        print(f"Balance before={before} after={after} last_gross_usd_used={last_gross}")

        if len(user2_entries) != 1:
            print(f"FAIL: expected 1 deduction entry, got {len(user2_entries)}")
            return 1
        deducted = float(user2_entries[0].get("tokens_deducted") or 0)
        if abs(deducted - expected_daily_gross) > 0.02:
            print(f"FAIL: expected tokens_deducted ~{expected_daily_gross}, got {deducted}")
            return 1
        if abs(last_gross - expected_daily_gross) > 0.02:
            print(f"FAIL: expected last_gross_usd_used ~{expected_daily_gross}, got {last_gross}")
            return 1
        if abs((before - after) - expected_daily_gross) > 0.02:
            print(f"FAIL: balance change expected ~{expected_daily_gross}, got {before - after}")
            return 1
        print("PASS: auto deduction test (4.41 deducted, last_gross_usd_used ~4.41)")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
