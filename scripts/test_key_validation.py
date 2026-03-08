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
    api_key = "96d1aea643c91ba4a7260702692e6e31d65bb69486f"
    api_secret = "e5f04a8af4f1a553b9f0cffaafd51f80b2cff9998c1"
    
    payload = Payload(bfx_key=api_key, bfx_secret=api_secret)
    res, err = await _validate_bitfinex_keys_only(payload)
    print("res:", res)
    print("err:", err)

if __name__ == "__main__":
    asyncio.run(test_validation())