import os
from pathlib import Path
from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_env_path)

from database import SessionLocal
import models
db = SessionLocal()
print("DATABASE_URL:", os.getenv("DATABASE_URL"))
print("User 2 email:", db.query(models.User).filter(models.User.id == 2).first().email)
print("User 2 has vault?", bool(db.query(models.User).filter(models.User.id == 2).first().vault))

# Let's actually test Bitfinex.
import asyncio
from services.bitfinex_service import BitfinexManager

async def test_api():
    u = db.query(models.User).filter(models.User.id == 2).first()
    if not u or not u.vault:
        return
    keys = u.vault.get_keys()
    print("Testing Bitfinex...")
    mgr = BitfinexManager(keys["bfx_key"], keys["bfx_secret"])
    res, err = await mgr.wallets()
    print("Wallets result:", type(res), len(res) if isinstance(res, list) else res)
    print("Wallets error:", err)

asyncio.run(test_api())
