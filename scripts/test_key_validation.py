import asyncio
import os
import sys

from pathlib import Path
from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_env_path)

from main import _validate_bitfinex_keys_only
from pydantic import BaseModel

class Payload(BaseModel):
    bfx_key: str
    bfx_secret: str

async def test_validation():
    api_key = os.getenv("TEST_BFX_KEY", "")
    api_secret = os.getenv("TEST_BFX_SECRET", "")
    if not api_key or not api_secret:
        print("ERROR: Set TEST_BFX_KEY and TEST_BFX_SECRET env vars.")
        return

    payload = Payload(bfx_key=api_key, bfx_secret=api_secret)
    res, err = await _validate_bitfinex_keys_only(payload)
    print("res:", res)
    print("err:", err)

if __name__ == "__main__":
    asyncio.run(test_validation())