"""
Run the bot engine for a user (using keys from DB) for a few seconds to verify keys work.
Usage: python scripts/test_bot_for_user.py [email]
Default: choiwangai@gmail.com
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
import models
from bot_engine import PortfolioManager

EMAIL = (sys.argv[1] if len(sys.argv) > 1 else "choiwangai@gmail.com").strip().lower()
RUN_SECONDS = 10


async def main():
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == EMAIL).first()
        if not user or not user.vault:
            print(f"User not found or no API keys: {EMAIL}")
            return 1
        keys = user.vault.get_keys()
        log_lines = []
        manager = PortfolioManager(
            user_id=user.id,
            api_key=keys["bfx_key"],
            api_secret=keys["bfx_secret"],
            gemini_key=keys.get("gemini_key", ""),
            redis_pool=None,
            log_lines=log_lines,
        )
        print(f"Running bot for {EMAIL} (user_id={user.id}) for {RUN_SECONDS}s...")
        task = asyncio.create_task(manager.scan_and_launch())
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=RUN_SECONDS)
        except asyncio.TimeoutError:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        print("--- Log lines (terminal output) ---")
        for L in log_lines:
            try:
                print(L)
            except UnicodeEncodeError:
                print(L.encode("ascii", errors="replace").decode("ascii"))
        print("--- OK: API keys run the bot.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
