"""
Test: when user 2's token balance is 0, the bot does not start / stops (worker token gate and kill-switch).

Steps:
1. Set user 2's tokens_remaining to 0 in the DB.
2. Run the worker task run_bot_task(ctx, 2) (same logic as ARQ).
3. Assert user 2's bot_status is "stopped" after the task returns.

The worker checks tokens at start: if tokens_remaining <= 0 it sets bot_status = "stopped" and returns
without starting the engine. So we never need a running bot; we only test the start gate.

Usage (from project root):
  python scripts/test_bot_stops_when_balance_zero_user2.py
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

USER_ID = 2


def main():
    import database
    import models
    from sqlalchemy import text
    from services import token_ledger_service as token_ledger_svc

    db = database.SessionLocal()
    try:
        # 1) Ensure user 2 has a token balance row and read current balance
        row = db.execute(
            text("SELECT user_id, tokens_remaining FROM user_token_balance WHERE user_id = :uid"),
            {"uid": USER_ID},
        ).fetchone()
        if not row:
            # Insert row with 0 so the test can run (user_id is PK)
            db.execute(
                text("""
                    INSERT INTO user_token_balance (user_id, tokens_remaining, purchased_tokens, updated_at)
                    VALUES (:uid, 0, 0, NOW())
                """),
                {"uid": USER_ID},
            )
            db.commit()
            print(f"Inserted user_token_balance row for user_id={USER_ID} with tokens_remaining=0")
        else:
            prev_balance = float(row[1] or 0)
            print(f"User {USER_ID} current tokens_remaining = {prev_balance}")

        # 2) Set tokens_remaining to 0
        db.execute(
            text("UPDATE user_token_balance SET tokens_remaining = 0, updated_at = NOW() WHERE user_id = :uid"),
            {"uid": USER_ID},
        )
        db.commit()
        print(f"Set user_id={USER_ID} tokens_remaining = 0")

        # Ensure user row is fresh for worker (worker will open its own session)
        db.expire_all()
    finally:
        db.close()

    # 3) Run the worker task (minimal ctx; redis=None so _term no-ops)
    async def run_test():
        from worker import run_bot_task
        ctx = {"redis": None, "job_id": "test-balance-zero"}
        await run_bot_task(ctx, USER_ID)

    asyncio.run(run_test())

    # 4) Assert bot_status is stopped
    db2 = database.SessionLocal()
    try:
        user = db2.query(models.User).filter(models.User.id == USER_ID).first()
        status = getattr(user, "bot_status", None) if user else None
        balance = token_ledger_svc.get_tokens_remaining(db2, USER_ID)
        if status == "stopped" and balance == 0:
            print("PASS: User 2 bot_status = 'stopped' and tokens_remaining = 0. Bot did not start (token gate).")
            return 0
        print(f"FAIL: User 2 bot_status = {status!r} (expected 'stopped'), tokens_remaining = {balance}")
        return 1
    finally:
        db2.close()


if __name__ == "__main__":
    sys.exit(main())
