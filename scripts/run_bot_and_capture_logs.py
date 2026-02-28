"""
Start the bot for user 2 via API, wait for worker to run, then read terminal_logs from Redis
to see the actual reason the worker reports. Requires: backend running, worker running, REDIS_URL in .env.
Usage: python scripts/run_bot_and_capture_logs.py [user_id]
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Load .env
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except ImportError:
    pass

USER_ID = int(sys.argv[1]) if len(sys.argv) > 1 else 2
API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
WAIT_SEC = 12


async def main_async():
    import requests
    from arq import create_pool
    from arq.connections import RedisSettings

    redis_url = os.getenv("REDIS_URL", "redis://localhost:6379")
    if not redis_url:
        print("REDIS_URL not set. Set it in .env")
        return 1

    try:
        settings = RedisSettings.from_dsn(redis_url)
        pool = await create_pool(settings)
    except Exception as e:
        print(f"   Redis connection failed: {e}")
        return 1

    # Clear old terminal lines so we only see this run's messages
    try:
        await pool.delete(f"terminal_logs:{USER_ID}")
        print("   Cleared terminal_logs (old messages removed).")
    except Exception as e:
        print(f"   (Could not clear: {e})")

    print(f"\n1. POST {API_BASE}/start-bot/{USER_ID} ...")
    try:
        r = requests.post(f"{API_BASE}/start-bot/{USER_ID}", timeout=15)
    except Exception as e:
        print(f"   Request failed: {e}")
        print("   Is the backend running? (uvicorn main:app --port 8000)")
        try: await pool.aclose()
        except Exception: pass
        return 1
    body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
    print(f"   Status: {r.status_code}")
    print(f"   Response: {body}")
    if r.status_code == 400:
        print("   -> API rejected start (e.g. insufficient tokens). No worker run.")
        try: await pool.aclose()
        except Exception: pass
        return 0
    if r.status_code == 404:
        print("   -> User or API keys not found.")
        try: await pool.aclose()
        except Exception: pass
        return 0
    if r.status_code != 200:
        print("   -> Unexpected status. Check backend.")
        try: await pool.aclose()
        except Exception: pass
        return 1

    print(f"\n2. Waiting {WAIT_SEC}s for worker to run and write terminal logs...")
    await asyncio.sleep(WAIT_SEC)

    print(f"\n3. Reading Redis key terminal_logs:{USER_ID} ...")
    try:
        lines = await pool.lrange(f"terminal_logs:{USER_ID}", 0, -1)
    except Exception as e:
        print(f"   LRANGE failed: {e}")
        try: await pool.aclose()
        except Exception: pass
        return 1
    try: await pool.aclose()
    except Exception: pass

    if not lines:
        print("   No lines. Worker may not have run yet (is ARQ worker running?) or job not picked up.")
        return 0
    print(f"   Found {len(lines)} line(s):\n")
    for i, line in enumerate(lines):
        decoded = line.decode("utf-8") if isinstance(line, bytes) else line
        try:
            print(f"   [{i+1}] {decoded}")
        except UnicodeEncodeError:
            print(f"   [{i+1}] {decoded.encode('ascii', errors='replace').decode('ascii')}")
    print("\n   ^-- Actual messages the worker wrote to the terminal tab.")
    return 0


def main():
    return asyncio.run(main_async())


if __name__ == "__main__":
    sys.exit(main())
