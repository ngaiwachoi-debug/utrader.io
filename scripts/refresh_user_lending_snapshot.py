"""
Refresh lending snapshot for a user (call Bitfinex ledgers API and update user_profit_snapshot).
Usage: python scripts/refresh_user_lending_snapshot.py 2
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
    user_id = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    import database
    from main import _refresh_user_lending_snapshot

    db = database.SessionLocal()
    try:
        result, rate_limited, _ = await _refresh_user_lending_snapshot(user_id, db)
        if rate_limited:
            print("Rate limited; using existing snapshot.")
        print(f"user_id={user_id} gross_profit={result.gross_profit} net_profit={result.net_profit} bitfinex_fee={result.bitfinex_fee}")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
