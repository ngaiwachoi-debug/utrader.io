"""
Run one lending cycle for user id 2 using API keys from the database.
Use this to verify the bot places orders (you should see [USD] TICKET ISSUED and [USDT] TICKET ISSUED in the output).

Run from project root: python scripts/run_one_cycle_user2.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import SessionLocal
import models
from lending_worker_engine import run_one_lending_cycle


async def main():
    user_id = 2
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            print(f"User id={user_id} not found.")
            return 1
        vault = db.query(models.APIVault).filter(models.APIVault.user_id == user_id).first()
        if not vault or not vault.encrypted_key or not vault.encrypted_secret:
            print(f"No API keys for user id={user_id}")
            return 1
        keys = vault.get_keys()
        gemini_key = keys.get("gemini_key", "") or ""

        print(f"Running one lending cycle for user {user_id} ({getattr(user, 'email', 'N/A')})...")
        print("-" * 60)
        success, log_lines = await run_one_lending_cycle(
            user_id=user_id,
            api_key=keys["bfx_key"],
            api_secret=keys["bfx_secret"],
            gemini_key=gemini_key,
            redis_pool=None,
        )
        print("-" * 60)
        for line in log_lines:
            print(line)
        print(f"Success: {success}")
        return 0 if success else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
