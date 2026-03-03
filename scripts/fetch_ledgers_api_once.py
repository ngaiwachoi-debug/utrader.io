"""
Fetch Bitfinex ledgers API once for user 2 and print raw response structure.
Usage: python scripts/fetch_ledgers_api_once.py [user_id]
No DB or snapshot writes; read-only for design.

Actual API response (v2/auth/r/ledgers/{currency}/hist):
  List of entries; each entry is a list of 9 elements:
  [0] = ID (int), [1] = CURRENCY (str e.g. 'USD'), [2] = WALLET (str e.g. 'funding'),
  [3] = MTS (int ms), [4] = None, [5] = AMOUNT (float), [6] = BALANCE (float),
  [7] = None, [8] = DESCRIPTION (str e.g. 'Margin Funding Payment on wallet funding')
  So entry[1] is currency and entry[5] is amount (entry[4] is None in practice).
"""
import asyncio
import json
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
    import models
    from services.bitfinex_service import BitfinexManager

    db = database.SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user or not getattr(user, "vault", None):
            print(f"No user or vault for user_id={user_id}")
            return 1
        keys = user.vault.get_keys()
        mgr = BitfinexManager(keys["bfx_key"], keys["bfx_secret"])

        # Fetch one currency (USD) with small limit to see structure
        print("=== Fetching v2/auth/r/ledgers/USD/hist limit=5 ===\n")
        entries, err = await mgr.ledgers_hist(currency="USD", limit=5)
        if err:
            print(f"Error: {err}")
            return 1
        if not isinstance(entries, list):
            print(f"Response type: {type(entries)}; value: {entries}")
            return 0

        print(f"Response: list of length {len(entries)}")
        for i, entry in enumerate(entries[:3]):
            print(f"\n--- Entry[{i}] (type={type(entry).__name__}, len={len(entry) if isinstance(entry, (list, tuple)) else 'N/A'}) ---")
            if isinstance(entry, (list, tuple)):
                for j, cell in enumerate(entry):
                    print(f"  [{j}] = {cell!r}")
            else:
                print(f"  {entry!r}")

        # Fetch USDT to see if structure differs
        print("\n=== Fetching v2/auth/r/ledgers/USDT/hist limit=3 ===\n")
        entries2, err2 = await mgr.ledgers_hist(currency="USDT", limit=3)
        if err2:
            print(f"USDT Error: {err2}")
        elif entries2 and len(entries2) > 0:
            print(f"USDT first entry length={len(entries2[0])}")
            for j, cell in enumerate(entries2[0]):
                print(f"  [{j}] = {cell!r}")

        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
