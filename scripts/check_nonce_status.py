"""Check if Redis nonce values match current time."""
import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
import redis

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

load_dotenv()

redis_url = os.getenv("NONCE_REDIS_URL") or os.getenv("REDIS_URL", "redis://localhost:6379")
redis_url = redis_url.strip('"').strip()
if not redis_url:
    print("ERROR: REDIS_URL not set")
    sys.exit(1)

r = redis.from_url(redis_url, decode_responses=True)

now_us = int(time.time() * 1000000)
now_readable = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

print(f"Current time (microseconds): {now_us}")
print(f"Current time (readable): {now_readable}")
print()

keys = r.keys("bitfinex_nonce:*")
print(f"Found {len(keys)} nonce keys:\n")

if not keys:
    print("No nonce keys found in Redis.")
    sys.exit(0)

for k in keys:
    nonce_val = r.get(k)
    if nonce_val:
        nonce_int = int(nonce_val)
        diff_us = nonce_int - now_us
        diff_sec = diff_us / 1000000
        
        status = "OK" if diff_sec >= 0 else "STALE"
        if diff_sec < -10:
            status = "VERY STALE (needs update)"
        
        print(f"{k}:")
        print(f"  Nonce value: {nonce_int}")
        print(f"  Difference: {diff_us:,} microseconds ({diff_sec:.2f} seconds)")
        print(f"  Status: {status}")
        print()
