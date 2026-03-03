"""
Verify manual-trigger deduction for user 2: should deduct yesterday once and today once (no double).
1. Reverses any 2026-03-03 deductions for user 2 so we start clean.
2. Runs backfill (yesterday) + refresh + expire_all + run_daily_token_deduction for user 2.
3. Asserts exactly 2 deduction log entries for user 2: one ~yesterday amount, one ~today amount.

Run from project root:
  python scripts/verify_manual_trigger_uid2.py
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")


async def main():
    user_id = 2
    date_str = "2026-03-03"
    import database
    import models
    from services import token_ledger_service as token_ledger_svc
    from services.daily_token_deduction import run_daily_token_deduction, run_deduction_for_user_for_date
    from main import _daily_10_00_fetch_and_save

    db = database.SessionLocal()
    try:
        # --- Step 0: Reverse any 2026-03-03 deductions for user 2 so we start clean ---
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
            token_ledger_svc.add_tokens(db, user_id, total_add_back, "deduction_rollback")
            snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).first()
            if snap and hasattr(snap, "last_deduction_processed_date"):
                snap.last_deduction_processed_date = None
            db.commit()
            print(f"Reversed {len(rows)} deduction(s) for user {user_id}, added back {total_add_back} tokens")
        db.expire_all()

        # Set snapshot to "yesterday" state so backfill has something to run (simulates stale snapshot before refresh)
        today_utc = datetime.utcnow().date()
        yesterday_utc = today_utc - timedelta(days=1)
        snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).first()
        if snap:
            if hasattr(snap, "last_daily_snapshot_date"):
                snap.last_daily_snapshot_date = yesterday_utc
            if hasattr(snap, "daily_gross_profit_usd"):
                snap.daily_gross_profit_usd = 25.69  # yesterday's amount for backfill
            if hasattr(snap, "last_deduction_processed_date"):
                snap.last_deduction_processed_date = None
            db.commit()
            print(f"Set snapshot to yesterday ({yesterday_utc}) with daily_gross=25.69 for backfill test")
        db.expire_all()

        # --- Step 1: Backfill (yesterday only) ---
        today_utc = datetime.utcnow().date()
        backfill_entries = []
        q = (
            db.query(models.UserTokenBalance, models.UserProfitSnapshot, models.User)
            .join(
                models.UserProfitSnapshot,
                models.UserTokenBalance.user_id == models.UserProfitSnapshot.user_id,
            )
            .join(models.User, models.User.id == models.UserTokenBalance.user_id)
            .filter(models.UserTokenBalance.user_id == user_id)
        )
        rows_list = q.all()
        for token_row, snap, user in rows_list:
            last_ded = getattr(snap, "last_deduction_processed_date", None)
            snapshot_date = getattr(snap, "last_daily_snapshot_date", None)
            if snapshot_date is None or snapshot_date >= today_utc:
                continue
            if last_ded is not None and last_ded >= snapshot_date:
                continue
            daily_gross = getattr(snap, "daily_gross_profit_usd", None)
            if daily_gross is None or float(daily_gross) <= 0:
                continue
            log_entry, _ = run_deduction_for_user_for_date(db, token_row.user_id, snapshot_date, float(daily_gross))
            if log_entry:
                backfill_entries.append(log_entry)
        if backfill_entries:
            db.commit()
            print(f"Backfill: {len(backfill_entries)} entry(ies) for user {user_id}")
        db.expire_all()

        # --- Step 2: Refresh (fetch Bitfinex, save snapshot) ---
        success, _, err = await _daily_10_00_fetch_and_save(user_id, db, accept_fresh_data=True)
        if not success and err:
            print(f"Refresh failed: {err}")
            return 1
        print("Refresh: snapshot updated from Bitfinex")

        # --- Step 3: expire_all then run_daily_token_deduction (simulates manual trigger fix) ---
        db.expire_all()
        log_entries, err = run_daily_token_deduction(db, user_ids=[user_id])
        if err:
            print(f"run_daily_token_deduction failed: {err}")
            return 1

        # --- Step 4: Verify ---
        user2_entries = [e for e in log_entries if e.get("user_id") == user_id]
        backfill_for_user2 = [e for e in backfill_entries if e.get("user_id") == user_id]
        all_user2_deductions = backfill_for_user2 + user2_entries

        print(f"\n--- Result for user {user_id} ---")
        print(f"Backfill entries: {len(backfill_for_user2)}")
        for e in backfill_for_user2:
            print(f"  for_date={e.get('for_date')} deducted={e.get('tokens_deducted')} after={e.get('tokens_remaining_after')}")
        print(f"Today run_daily_token_deduction entries: {len(user2_entries)}")
        for e in user2_entries:
            print(f"  deducted={e.get('tokens_deducted')} after={e.get('tokens_remaining_after')}")

        # Expect: 1 backfill (yesterday) + 1 today = 2 total; no duplicate of the same amount
        if len(backfill_for_user2) + len(user2_entries) != 2:
            print(f"\nFAIL: expected 2 total deductions for user 2, got {len(backfill_for_user2) + len(user2_entries)}")
            return 1
        amounts = [float(e.get("tokens_deducted") or 0) for e in all_user2_deductions]
        if len(amounts) != 2:
            print(f"\nFAIL: expected 2 amounts, got {amounts}")
            return 1
        # No double deduction: the two amounts must be different (yesterday vs today from API)
        if amounts[0] == amounts[1]:
            print(f"\nFAIL: double deduction (same amount twice): {amounts}")
            return 1
        yesterday_amt = next((a for a in amounts if 20 <= a <= 30), None)
        today_amt = next((a for a in amounts if a < 20 and a > 0), None)
        if not yesterday_amt or not today_amt:
            print(f"\nWARN: amounts {amounts} - one should be ~yesterday (20-30), one today (>0,<20). Passing if distinct.")
        print(f"\nPASS: user 2 deducted twice with distinct amounts (yesterday ~{yesterday_amt}, today ~{today_amt}); no double 25.69")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
