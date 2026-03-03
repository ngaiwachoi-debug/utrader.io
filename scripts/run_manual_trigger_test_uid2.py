"""
After rolling back user 2 for today: run manual-trigger flow (yesterday 26.83 + today 4.41).
1. Set snapshot yesterday 26.83, run backfill for yesterday.
2. Set snapshot today 4.41, run run_daily_token_deduction.
Verify two deduction records and last_gross_usd_used ~4.41. Then rollback once more.

  python scripts/rollback_uid2_two_days.py   # first
  python scripts/run_manual_trigger_test_uid2.py
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
    yesterday_gross = 26.83
    today_gross = 4.41

    import database
    import models
    from services import token_ledger_service as token_ledger_svc
    from services.daily_token_deduction import run_daily_token_deduction, run_deduction_for_user_for_date

    db = database.SessionLocal()
    try:
        today_utc = datetime.utcnow().date()
        yesterday_utc = today_utc - timedelta(days=1)
        snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).first()
        if not snap:
            print("No user_profit_snapshot for user 2")
            return 1

        # 1. Backfill yesterday (26.83)
        snap.daily_gross_profit_usd = yesterday_gross
        if hasattr(snap, "last_daily_snapshot_date"):
            snap.last_daily_snapshot_date = yesterday_utc
        if hasattr(snap, "last_deduction_processed_date"):
            snap.last_deduction_processed_date = None
        db.commit()
        db.expire_all()

        log_entry, _ = run_deduction_for_user_for_date(db, user_id, yesterday_utc, yesterday_gross)
        if not log_entry:
            print("Backfill produced no log entry")
            return 1
        db.commit()
        db.expire_all()
        print(f"Backfill yesterday: deducted {log_entry.get('tokens_deducted')}")

        # 2. Today (4.41)
        snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).first()
        snap.daily_gross_profit_usd = today_gross
        if hasattr(snap, "last_daily_snapshot_date"):
            snap.last_daily_snapshot_date = today_utc
        if hasattr(snap, "last_deduction_processed_date"):
            snap.last_deduction_processed_date = None
        db.commit()
        db.expire_all()

        log_entries, err = run_daily_token_deduction(db, user_ids=[user_id])
        if err:
            print(f"run_daily_token_deduction failed: {err}")
            return 1
        user2_today = [e for e in log_entries if e.get("user_id") == user_id]
        if len(user2_today) != 1:
            print(f"FAIL: expected 1 today entry, got {len(user2_today)}")
            return 1
        db.commit()

        # 3. Verify
        tb = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).first()
        last_gross = float(tb.last_gross_usd_used or 0) if tb else 0
        deduction_rows = (
            db.query(models.DeductionLog)
            .filter(models.DeductionLog.user_id == user_id)
            .order_by(models.DeductionLog.timestamp_utc.desc())
            .limit(5)
            .all()
        )
        amounts = [float(r.tokens_deducted or 0) for r in deduction_rows]
        print(f"last_gross_usd_used={last_gross}, recent deduction_log amounts={amounts}")

        if abs(last_gross - today_gross) > 0.02:
            print(f"FAIL: last_gross_usd_used expected ~{today_gross}, got {last_gross}")
            return 1
        if not any(abs(a - yesterday_gross) < 0.02 for a in amounts) or not any(abs(a - today_gross) < 0.02 for a in amounts):
            print(f"FAIL: expected deduction_log to contain ~{yesterday_gross} and ~{today_gross}, got {amounts}")
            return 1
        print("PASS: manual trigger test (26.83 + 4.41, last_gross_usd_used ~4.41)")

        # 4. Rollback once more (today and yesterday)
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
                print(f"Rollback {date_str}: added back {total_add_back}")
        snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).first()
        if snap and hasattr(snap, "last_deduction_processed_date"):
            snap.last_deduction_processed_date = None
        db.commit()
        print("Rollback complete (two days removed again).")
        return 0
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
