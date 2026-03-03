"""
One-off: reverse deductions for users 32, 2, 3 for date 2026-03-03 so you can test manual trigger again.
Adds back tokens (from deduction_log sum per user) and clears last_deduction_processed_date.

Run from project root:
  python scripts/reverse_deductions_2026_03_03.py
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
    import database
    import models
    from services import token_ledger_service as token_ledger_svc

    date_str = "2026-03-03"
    user_ids = [32, 2, 3]
    day_start = datetime.fromisoformat(date_str + "T00:00:00")
    day_end = datetime.fromisoformat(date_str + "T23:59:59.999999")

    db = database.SessionLocal()
    try:
        for user_id in user_ids:
            rows = (
                db.query(models.DeductionLog)
                .filter(
                    models.DeductionLog.user_id == user_id,
                    models.DeductionLog.timestamp_utc >= day_start,
                    models.DeductionLog.timestamp_utc <= day_end,
                )
                .all()
            )
            if not rows:
                print(f"User {user_id}: no deduction_log rows for {date_str}, skipping")
                continue
            total_add_back = sum(float(r.tokens_deducted or 0) for r in rows)
            new_remaining = token_ledger_svc.add_tokens(db, user_id, total_add_back, "deduction_rollback")
            snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).first()
            if snap and hasattr(snap, "last_deduction_processed_date"):
                snap.last_deduction_processed_date = None
            print(f"User {user_id}: added back {total_add_back}, new tokens_remaining={new_remaining}")
        db.commit()
        print("Done. You can run manual trigger again to test.")
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        return 1
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
