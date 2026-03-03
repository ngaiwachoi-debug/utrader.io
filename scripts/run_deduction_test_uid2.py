"""
Deduction test for a single user (default uid 2): refresh snapshot (10:00-style) then optionally run deduction.
Use this to verify manual-trigger / soft-pad flow without admin API.

Usage:
  python scripts/run_deduction_test_uid2.py [user_id]              # refresh + dry-run (no deduct)
  python scripts/run_deduction_test_uid2.py [user_id] --apply      # refresh + run deduction for this user only
"""
import asyncio
import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")


async def main():
    parser = argparse.ArgumentParser(description="Run deduction test: refresh snapshot then optionally deduct for one user.")
    parser.add_argument("user_id", type=int, nargs="?", default=2, help="User ID (default 2)")
    parser.add_argument("--apply", action="store_true", help="Actually run deduction for this user; default is dry-run.")
    args = parser.parse_args()
    user_id = args.user_id
    do_deduct = args.apply

    import database
    import models
    from services.daily_token_deduction import run_daily_token_deduction, run_deduction_for_user_for_date
    from main import _daily_10_00_fetch_and_save

    db = database.SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user or not getattr(user, "vault", None):
            print(f"No user or vault for user_id={user_id}")
            return 1
        email = getattr(user, "email", None) or ""
        snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).first()
        token_row = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).first()
        today = datetime.utcnow().date()

        print("=" * 60)
        print(f"DEDUCTION TEST – user_id={user_id} ({email})")
        print("=" * 60)
        print(f"UTC date: {today}")
        print()

        # --- Before ---
        print("--- BEFORE (current snapshot & balance) ---")
        if snap:
            print(f"  daily_gross_profit_usd:    {getattr(snap, 'daily_gross_profit_usd', None)}")
            print(f"  last_daily_snapshot_date:  {getattr(snap, 'last_daily_snapshot_date', None)}")
            print(f"  last_deduction_processed_date: {getattr(snap, 'last_deduction_processed_date', None)}")
            print(f"  gross_profit_usd:          {getattr(snap, 'gross_profit_usd', None)}")
            print(f"  snapshot updated_at:       {getattr(snap, 'updated_at', None)}")
        else:
            print("  (no snapshot row)")
        if token_row:
            print(f"  tokens_remaining:          {getattr(token_row, 'tokens_remaining', None)}")
            print(f"  last_gross_usd_used:      {getattr(token_row, 'last_gross_usd_used', None)}")
        else:
            print("  (no token balance row)")
        print()

        # --- Step 0 (when --apply): Backfill missed snapshot day before refresh ---
        if do_deduct and snap and token_row:
            last_ded = getattr(snap, "last_deduction_processed_date", None)
            snapshot_date = getattr(snap, "last_daily_snapshot_date", None)
            daily_gross = getattr(snap, "daily_gross_profit_usd", None)
            if snapshot_date is not None and (last_ded is None or last_ded < snapshot_date) and daily_gross is not None and float(daily_gross) > 0:
                print("--- STEP 0: Backfill missed snapshot day (before refresh) ---")
                log_entry, err = run_deduction_for_user_for_date(db, user_id, snapshot_date, float(daily_gross))
                if err:
                    print(f"  Backfill FAILED: {err}")
                    return 1
                if log_entry:
                    db.commit()
                    print(f"  Backfilled: for_date={snapshot_date} deducted {log_entry.get('tokens_deducted')} -> remaining {log_entry.get('tokens_remaining_after')}")
                else:
                    print("  No backfill (already deducted for that date or skip).")
                print()
                snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).first()

        # --- Step 1: Refresh snapshot (10:00-style for this user only) ---
        print("--- STEP 1: Refresh snapshot from Bitfinex (10:00-style) ---")
        success, data_incomplete, err = await _daily_10_00_fetch_and_save(user_id, db)
        if err and not success:
            print(f"  FAILED: {err}")
            return 1
        if data_incomplete:
            print("  Data incomplete (latest entry < 20 mins). Snapshot not updated.")
        else:
            print("  OK – snapshot updated.")
        print()

        # --- After refresh ---
        snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).first()
        token_row = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).first()
        print("--- AFTER REFRESH ---")
        if snap:
            print(f"  daily_gross_profit_usd:    {getattr(snap, 'daily_gross_profit_usd', None)}")
            print(f"  gross_profit_usd:          {getattr(snap, 'gross_profit_usd', None)}")
        print()

        # --- Step 2: Deduction (dry-run or apply) ---
        if do_deduct:
            print("--- STEP 2: Run deduction for this user (--apply) ---")
            log_entries, err = run_daily_token_deduction(db, user_ids=[user_id])
            if err:
                print(f"  FAILED: {err}")
                return 1
            if log_entries:
                e = log_entries[0]
                print(f"  Deducted: gross_profit={e.get('gross_profit')} tokens_deducted={e.get('tokens_deducted')}")
                print(f"  tokens_remaining: {e.get('tokens_remaining_before')} -> {e.get('tokens_remaining_after')}")
            else:
                print("  No deduction (already processed today or daily_gross <= 0).")
        else:
            print("--- STEP 2: Dry-run (no deduction). Use --apply to actually deduct. ---")
        print()
        print("Done.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
