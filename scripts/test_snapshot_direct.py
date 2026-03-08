import asyncio
import os
import sys

from pathlib import Path
from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_env_path)

from database import SessionLocal
import models
from services.bitfinex_service import BitfinexManager
from main import _portfolio_allocation_snapshot

async def test_snapshot():
    db = SessionLocal()
    user = db.query(models.User).filter(models.User.id == 2).first()
    keys = user.vault.get_keys()
    
    mgr = BitfinexManager(keys["bfx_key"], keys["bfx_secret"])
    print("Fetching snapshot...")
    res, log_str, rate_limited = await _portfolio_allocation_snapshot(mgr, None)
    
    print("Result:", res)
    print("Log string:", log_str)
    print("Rate limited:", rate_limited)

if __name__ == "__main__":
    asyncio.run(test_snapshot())