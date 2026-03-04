"""
Option 3: Run the full 10:30 UTC flow once (final fetch + 09:00 cache + expire_all + run_daily_token_deduction).
Uses real DB; optional Redis and Bitfinex API for final fetch.

Run from project root:
  python scripts/run_full_1030_flow_once.py
"""
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")


async def main():
    from datetime import datetime

    import database
    import models
    from main import (
        _daily_10_00_fetch_and_save,
        _apply_09_00_cache_before_deduction,
        get_redis,
        _get_scheduler_test_user_id,
        _get_deduction_multiplier,
        DELAY_BETWEEN_USERS_SEC,
        REDIS_CONNECT_TIMEOUT,
    )
    from services.daily_token_deduction import run_daily_token_deduction

    db = database.SessionLocal()
    try:
        today_utc = datetime.utcnow().date()
        user_ids_with_vault = [
            row[0]
            for row in db.query(models.User.id)
            .join(models.APIVault, models.User.id == models.APIVault.user_id)
            .distinct()
            .all()
        ]
        test_uid = _get_scheduler_test_user_id()
        if test_uid is not None:
            user_ids_with_vault = [u for u in user_ids_with_vault if u == test_uid]
        need_fetch = []
        for uid in user_ids_with_vault:
            snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == uid).first()
            if snap is None:
                need_fetch.append(uid)
            else:
                snapshot_date = getattr(snap, "last_daily_snapshot_date", None)
                if snapshot_date is None or snapshot_date != today_utc:
                    need_fetch.append(uid)
        if need_fetch:
            print(f"10:30 final fetch for {len(need_fetch)} user(s) with snapshot not for today")
            for i, uid in enumerate(need_fetch):
                if i > 0:
                    await asyncio.sleep(DELAY_BETWEEN_USERS_SEC)
                db_u = database.SessionLocal()
                try:
                    success, _, _ = await _daily_10_00_fetch_and_save(uid, db_u, accept_fresh_data=True)
                    if success:
                        print(f"  user_id={uid} fetch OK")
                finally:
                    db_u.close()
        try:
            redis = await asyncio.wait_for(get_redis(), timeout=REDIS_CONNECT_TIMEOUT)
            await _apply_09_00_cache_before_deduction(db, redis)
            print("09:00 cache applied")
        except Exception as e:
            print(f"09:00 cache skipped: {e}")
        db.expire_all()
        mult = _get_deduction_multiplier(db)
        log_entries, err = run_daily_token_deduction(db, deduction_multiplier=mult)
        if err:
            print(f"FAIL: run_daily_token_deduction: {err}")
            return 1
        print(f"run_daily_token_deduction: {len(log_entries)} entry(ies)")
        for e in log_entries:
            print(f"  user_id={e.get('user_id')} tokens_deducted={e.get('tokens_deducted')} after={e.get('tokens_remaining_after')}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
