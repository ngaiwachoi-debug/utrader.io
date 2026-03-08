"""
Run the worker's run_bot_task for a user IN-PROCESS (no ARQ) to see exact failure reason.
Uses same DB and Redis as real worker. No job queue.
Usage: python scripts/run_worker_task_inprocess.py [user_id]
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
_env_path = Path(__file__).resolve().parent.parent / ".env"
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=_env_path)
except ImportError:
    pass

USER_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 2


async def main():
    from arq import create_pool
    from arq.connections import RedisSettings
    from database import SessionLocal
    import models
    from worker import run_bot_task, _tokens_remaining_for_user

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    print("Redis: connected via REDIS_URL")
    print(f"User ID: {USER_ID}\n")

    settings = RedisSettings.from_dsn(redis_url)
    pool = await create_pool(settings)
    ctx = {"redis": pool, "job_id": "inprocess_test"}

    # Pre-check what DB has (same as worker will see)
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.id == USER_ID).first()
        print("--- DB state (what worker will see) ---")
        print(f"  user exists: {user is not None}")
        if user:
            print(f"  user.vault exists: {getattr(user, 'vault', None) is not None}")
            tokens = _tokens_remaining_for_user(db, USER_ID)
            print(f"  _tokens_remaining_for_user(db, {USER_ID}) = {tokens}")
        else:
            print("  (no user)")
        db.close()
    except Exception as e:
        print(f"  DB error: {e}")
        db.close()

    print("\n--- Running run_bot_task(ctx, {}) (will exit after token check or first _term) ---\n".format(USER_ID))

    # Run the real task (it will _term to Redis and we'll read it after)
    try:
        task = asyncio.create_task(run_bot_task(ctx, USER_ID))
        await asyncio.wait_for(task, timeout=15.0)
    except asyncio.TimeoutError:
        print("[Timeout - task still running (engine started). That is OK.)")
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    except Exception as e:
        print(f"[Exception] {e}")

    # Show what was written to terminal_logs
    print("\n--- Terminal logs written by worker ---")
    try:
        lines = await pool.lrange(f"terminal_logs:{USER_ID}", -6, -1)  # last 6
        for line in (lines or []):
            decoded = line.decode("utf-8") if isinstance(line, bytes) else line
            print(f"  {decoded}")
    except Exception as e:
        print(f"  Error reading Redis: {e}")
    try:
        if hasattr(pool, "aclose"):
            await pool.aclose()
        else:
            await pool.close()
    except Exception:
        pass


if __name__ == "__main__":
    asyncio.run(main())
