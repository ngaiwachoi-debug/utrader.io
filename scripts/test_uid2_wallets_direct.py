import asyncio
import os
import sys

# Setup environment
from dotenv import load_dotenv
load_dotenv()

from database import SessionLocal
import models
from services.bitfinex_service import BitfinexManager

async def test_wallets():
    db = SessionLocal()
    user = db.query(models.User).filter(models.User.id == 2).first()
    if not user or not user.vault:
        print("No user 2 or no vault")
        return
    
    keys = user.vault.get_keys()
    mgr = BitfinexManager(keys["bfx_key"], keys["bfx_secret"])
    
    print("Fetching wallets for user 2...")
    res, err = await mgr.wallets()
    print(f"Result: {res}")
    print(f"Error: {err}")

if __name__ == "__main__":
    asyncio.run(test_wallets())
