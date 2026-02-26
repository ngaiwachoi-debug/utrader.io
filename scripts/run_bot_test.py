"""
Run one lending cycle with the given Bitfinex API keys and print terminal-style output.
Use this to verify the bot runs and shows Deploying / TICKET ISSUED etc.

Usage (from project root):
  python scripts/run_bot_test.py

Set env BFX_KEY, BFX_SECRET, GEMINI_KEY to override defaults below.
"""
import asyncio
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BFX_KEY = os.getenv("BFX_KEY", "4b7e10b7478dbd2de2b8a402cf155e0dfd47685292f")
BFX_SECRET = os.getenv("BFX_SECRET", "3be479ee822ee34054d5587861bf3f3c2f14f33ecf3")
GEMINI_KEY = os.getenv("GEMINI_KEY", "")


async def main():
    # 1) Test connection with backend's BitfinexManager (same as API uses)
    print("=" * 60)
    print("Step 1: Testing Bitfinex connection (auth/r/wallets)...")
    print("=" * 60)
    from services.bitfinex_service import BitfinexManager

    mgr = BitfinexManager(BFX_KEY, BFX_SECRET)
    wallets, err = await mgr.wallets()
    if err:
        print(f"Connection failed: {err}")
        return 1
    if not wallets:
        print("Wallets: (empty)")
    else:
        # Bitfinex returns list of arrays [type, currency, balance, ...]
        funding = [w for w in wallets if isinstance(w, (list, tuple)) and len(w) >= 3 and w[0] == "funding" and float(w[2] or 0) > 0]
        print(f"Wallets OK. Funding with balance: {len(funding)}")
        for w in funding[:5]:
            print(f"  {w[1]}: {w[2]}")

    # 2) Run one lending cycle (bot_engine)
    print("\n" + "=" * 60)
    print("Step 2: Running one lending cycle (scan + deploy)...")
    print("=" * 60)
    from lending_worker_engine import run_one_lending_cycle

    success, lines = await run_one_lending_cycle(
        user_id=0,
        api_key=BFX_KEY,
        api_secret=BFX_SECRET,
        gemini_key=GEMINI_KEY,
        redis_pool=None,
    )
    print("\n--- Terminal output (what would appear in UI) ---")
    for line in lines:
        print(line)
    print("---")
    print(f"Success: {success}")
    return 0 if success else 1


if __name__ == "__main__":
    try:
        exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\nStopped.")
        exit(130)
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
