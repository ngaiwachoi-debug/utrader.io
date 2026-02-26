"""
Test Bitfinex API response for a user (e.g. choiwangai@gmail.com).
Uses stored API keys from DB and the same portfolio allocation snapshot as the
Dashboard (wallets + funding/credits + funding/offers, all in USD).

Run from project root:
  python scripts/test_bitfinex_for_user.py
  python scripts/test_bitfinex_for_user.py choiwangai@gmail.com
"""
import asyncio
import sys
from pathlib import Path

# project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import SessionLocal
import models
from services.bitfinex_service import BitfinexManager
from main import _portfolio_allocation_snapshot


async def main():
    email = (sys.argv[1] if len(sys.argv) > 1 else "choiwangai@gmail.com").strip()
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        if not user:
            print(f"User not found: {email}")
            return
        vault = db.query(models.APIVault).filter(models.APIVault.user_id == user.id).first()
        if not vault or not vault.encrypted_key or not vault.encrypted_secret:
            print(f"No API keys for {email}")
            return
        keys = vault.get_keys()
        mgr = BitfinexManager(keys["bfx_key"], keys["bfx_secret"])
        print(f"Bitfinex portfolio allocation test for {email} (user_id={user.id})")
        print("-" * 60)
        summary, log_str, rate_limited = await _portfolio_allocation_snapshot(mgr)
        if rate_limited:
            print("Rate limited by Bitfinex; try again later.")
        print(log_str)
        print("-" * 60)
        print("Dashboard mapping:")
        print(f"  Actively Earning (Return Generating): ${summary.get('total_lent_usd', 0):,.2f}")
        print(f"  Pending Deployment (In Order Book):   ${summary.get('total_offers_usd', 0):,.2f}")
        print(f"  Idle Funds (Cash Drag):               ${summary.get('idle_usd', 0):,.2f}")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
