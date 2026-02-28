"""
Run run_bot_task in-process (no ARQ queue), clear terminal_logs first, run 8s, then print
terminal_logs. Proves worker logic + token check work with current .env/DB.
"""
import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
load_dotenv = getattr(__import__("dotenv", fromlist=["load_dotenv"]), "load_dotenv", None)
if load_dotenv:
    load_dotenv(Path(__file__).resolve().parent.parent / ".env")

USER_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 2

async def main():
    from arq import create_pool
    from arq.connections import RedisSettings
    from worker import run_bot_task

    redis_url = os.getenv("REDIS_URL")
    if not redis_url:
        print("REDIS_URL not set")
        return 1
    settings = RedisSettings.from_dsn(redis_url)
    pool = await create_pool(settings)
    await pool.delete(f"terminal_logs:{USER_ID}")
    print(f"Cleared terminal_logs:{USER_ID}")

    ctx = {"redis": pool, "job_id": "direct_test"}
    task = asyncio.create_task(run_bot_task(ctx, USER_ID))
    try:
        await asyncio.wait_for(task, timeout=8.0)
    except asyncio.TimeoutError:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    lines = await pool.lrange(f"terminal_logs:{USER_ID}", 0, -1)
    await pool.aclose()

    print(f"\nTerminal logs ({len(lines or [])} lines):")
    for i, L in enumerate(lines or []):
        d = L.decode("utf-8") if isinstance(L, bytes) else L
        try:
            print(f"  [{i+1}] {d}")
        except UnicodeEncodeError:
            print(f"  [{i+1}] {d.encode('ascii', errors='replace').decode()}")
    return 0

if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
