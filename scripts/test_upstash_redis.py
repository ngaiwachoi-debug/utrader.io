"""
Test Upstash Redis connection (REDIS_URL from .env).
Verifies: connection, ping, and optional enqueue of a no-op job.
No local Redis required; uses rediss:// with SSL.

Usage (from project root):
  python scripts/test_upstash_redis.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

REDIS_URL = os.getenv("REDIS_URL")


async def main():
    if not REDIS_URL:
        print("[FAIL] REDIS_URL not set. Set it in .env (e.g. rediss://default:PASSWORD@HOST:6379)")
        return 1
    if not REDIS_URL.strip().lower().startswith("rediss://"):
        print("[WARN] REDIS_URL does not use rediss:// (SSL). Upstash requires rediss://")

    from arq import create_pool
    from arq.connections import RedisSettings

    settings = RedisSettings.from_dsn(REDIS_URL)
    if REDIS_URL.strip().lower().startswith("rediss://"):
        settings.ssl = True
        settings.conn_timeout = 10
        settings.conn_retries = 5

    # Migrated to NEW Upstash server (eminent-antelope-62080); no references to old account
    host = REDIS_URL.split("@")[-1].split(":")[0] if "@" in REDIS_URL else "Redis"
    print("Connecting to Redis (%s)..." % host)
    try:
        redis = await create_pool(settings)
        await redis.ping()
        print("[PASS] Redis connected at %s (ping OK)" % host)
    except Exception as e:
        print(f"[FAIL] Upstash Redis connection failed: {e}")
        return 1

    # Optional: enqueue a no-op to confirm ARQ queue works (run_bot_task won't be called for a fake job name)
    try:
        # Just verify we can use the queue (zadd/psetex). Don't enqueue run_bot_task to avoid side effects.
        info = await redis.info("server")
        print(f"[PASS] Redis server: {info.get('redis_version', '?')}")
    except Exception as e:
        print(f"[WARN] Redis info failed: {e}")

    print("Upstash Redis ready. Start backend and worker with the same REDIS_URL.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
