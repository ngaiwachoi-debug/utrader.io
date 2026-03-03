"""
Reverse today's deductions and set last_deduction_processed_date to YESTERDAY
so manual trigger will see "yesterday already deducted" and only deduct today.

Run from project root:
  python scripts/reverse_today_set_yesterday_deducted.py
"""
import os
import sys
from datetime import datetime, timedelta, timezone
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

    today = datetime.now(timezone.utc).date()
    yesterday = today - timedelta(days=1)
    day_start = datetime.fromisoformat(today.isoformat() + "T00:00:00")
    day_end = datetime.fromisoformat(today.isoformat() + "T23:59:59.999999")

    db = database.SessionLocal()
    try:
        rows = (
            db.query(models.DeductionLog)
            .filter(
                models.DeductionLog.timestamp_utc >= day_start,
                models.DeductionLog.timestamp_utc <= day_end,
            )
            .all()
        )
        if not rows:
            print(f"No deduction_log rows for today ({today}). Nothing to reverse.")
            return 0
        by_user = {}
        for r in rows:
            uid = r.user_id
            if uid not in by_user:
                by_user[uid] = 0.0
            by_user[uid] += float(r.tokens_deducted or 0)
        for user_id, total_add_back in by_user.items():
            total_add_back = round(total_add_back, 2)
            token_ledger_svc.add_tokens(db, user_id, total_add_back, "deduction_rollback")
            snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).first()
            if snap and hasattr(snap, "last_deduction_processed_date"):
                snap.last_deduction_processed_date = yesterday
            new_remaining = token_ledger_svc.get_tokens_remaining(db, user_id)
            print(f"User {user_id}: added back {total_add_back}, last_deduction_processed_date -> {yesterday}, tokens_remaining={new_remaining}")
        db.commit()
        print(f"\nDone. Manual trigger should now only deduct today ({today}); yesterday ({yesterday}) is already marked as processed.")
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        return 1
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
