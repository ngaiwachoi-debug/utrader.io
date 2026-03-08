"""
Clear bot run lock for a user (if stuck/stale).

The bot uses a Redis lock (bot_run_lock:{user_id}) to prevent multiple concurrent runs.
This lock has a 90-second TTL and is renewed every 30 seconds while the bot is running.
If the bot crashes or stops unexpectedly, the lock should expire automatically.

However, if you need to clear a stale lock manually, use this script.

Usage:
    python scripts/clear_bot_lock.py 2
    python scripts/clear_bot_lock.py 2 --force
"""

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
import redis

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

load_dotenv()

redis_url = os.getenv("REDIS_URL", "redis://localhost:6379").strip('"')
if not redis_url:
    print("ERROR: REDIS_URL not set")
    sys.exit(1)

r = redis.from_url(redis_url, decode_responses=True)

BOT_RUN_LOCK_PREFIX = "bot_run_lock:"


def main():
    parser = argparse.ArgumentParser(
        description="Clear bot run lock for a user (prevents concurrent bot runs)"
    )
    parser.add_argument("user_id", type=int, help="User ID")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Force clear even if lock exists (default: check first)",
    )
    args = parser.parse_args()

    lock_key = f"{BOT_RUN_LOCK_PREFIX}{args.user_id}"

    # Check if lock exists
    lock_val = r.get(lock_key)
    ttl = r.ttl(lock_key)

    if lock_val:
        print(f"Lock exists for user {args.user_id}:")
        print(f"  Key: {lock_key}")
        print(f"  Value: {lock_val}")
        print(f"  TTL: {ttl} seconds ({'expires soon' if ttl < 30 else 'still valid'})")
        print()

        if not args.force:
            print("Lock is active. Use --force to clear it anyway.")
            print("Note: Only clear if you're sure the bot is not running!")
            return 1

        print("Clearing lock (--force)...")
    else:
        print(f"No lock found for user {args.user_id}")
        return 0

    # Clear the lock
    deleted = r.delete(lock_key)
    if deleted:
        print(f"✓ Lock cleared successfully for user {args.user_id}")
        print("You can now start the bot again.")
        return 0
    else:
        print("Failed to clear lock")
        return 1


if __name__ == "__main__":
    sys.exit(main())
