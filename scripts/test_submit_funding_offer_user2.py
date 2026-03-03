"""
Test that user 2 can submit one funding offer to Bitfinex (same payload as bot).
Submits a minimal LIMIT offer then cancels it. Run from project root: python scripts/test_submit_funding_offer_user2.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import SessionLocal
import models
from services.bitfinex_service import BitfinexManager


async def main():
    user_id = 2
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            print(f"User id={user_id} not found.")
            return 1
        vault = db.query(models.APIVault).filter(models.APIVault.user_id == user_id).first()
        if not vault or not vault.encrypted_key or not vault.encrypted_secret:
            print(f"No API keys for user id={user_id}")
            return 1
        keys = vault.get_keys()
        mgr = BitfinexManager(keys["bfx_key"], keys["bfx_secret"])

        # Same payload shape as bot: type, symbol, amount, rate, period (Bitfinex required)
        payload = {
            "type": "LIMIT",
            "symbol": "fUSD",
            "amount": "150",
            "rate": "0.0001",
            "period": 2,
        }
        # BitfinexManager uses _post(endpoint, payload); endpoint is "v2/auth/..."
        result, err = await mgr._post("v2/auth/w/funding/offer/submit", payload)
        if err:
            print(f"Submit FAILED: {err}")
            return 1
        print("Submit SUCCESS: Bitfinex accepted the offer.")
        # Parse offer id from response and cancel so we don't leave a test order
        offer_id = None
        if isinstance(result, list) and len(result) > 4 and isinstance(result[4], list) and len(result[4]) > 0:
            offer_id = result[4][0]
        if offer_id is not None:
            cancel_res, cancel_err = await mgr._post("v2/auth/w/funding/offer/cancel", {"id": offer_id})
            if cancel_err:
                print(f"Cancel test offer failed (offer id {offer_id}): {cancel_err}")
            else:
                print(f"Cancelled test offer id={offer_id}.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
