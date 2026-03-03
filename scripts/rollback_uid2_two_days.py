"""
Rollback user 2 deduction for today and yesterday: add tokens back, delete deduction_log rows,
clear last_deduction_processed_date. Use before testing auto/manual deduction.

  python scripts/rollback_uid2_two_days.py
"""
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")


def main():
    user_id = 2
    import database
    import models
    from services import token_ledger_service as token_ledger_svc

    db = database.SessionLocal()
    try:
        today_utc = datetime.utcnow().date()
        yesterday_utc = today_utc - timedelta(days=1)
        for date_d in (yesterday_utc, today_utc):
            date_str = date_d.isoformat()
            day_start = datetime.fromisoformat(date_str + "T00:00:00")
            day_end = datetime.fromisoformat(date_str + "T23:59:59.999999")
            rows = (
                db.query(models.DeductionLog)
                .filter(
                    models.DeductionLog.user_id == user_id,
                    models.DeductionLog.timestamp_utc >= day_start,
                    models.DeductionLog.timestamp_utc <= day_end,
                )
                .all()
            )
            if rows:
                total_add_back = sum(float(r.tokens_deducted or 0) for r in rows)
                for r in rows:
                    db.delete(r)
                token_ledger_svc.add_tokens(db, user_id, total_add_back, "deduction_rollback")
                print(f"User {user_id} date {date_str}: rolled back {total_add_back} tokens, removed {len(rows)} deduction_log row(s)")
            else:
                print(f"User {user_id} date {date_str}: no deduction_log rows")

        snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).first()
        if snap and hasattr(snap, "last_deduction_processed_date"):
            snap.last_deduction_processed_date = None
            print(f"User {user_id}: cleared last_deduction_processed_date")
        db.commit()
        return 0
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
