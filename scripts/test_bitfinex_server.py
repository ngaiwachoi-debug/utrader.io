"""
Test Bitfinex API from server using the same logic as the bot (bitfinex_service).
Uses env vars so keys are not committed:
  BFTEST_KEY    - Bitfinex API key
  BFTEST_SECRET - Bitfinex API secret

Usage (from project root):
  $env:BFTEST_KEY="your_key"; $env:BFTEST_SECRET="your_secret"; python scripts/test_bitfinex_server.py

Then optionally update choiwangai vault (backend must be running with ALLOW_DEV_CONNECT=1):
  $env:ALLOW_DEV_UPDATE="1"; ... python scripts/test_bitfinex_server.py
"""
import os
import sys

_script_dir = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_script_dir)
if _root not in sys.path:
    sys.path.insert(0, _root)

from services.bitfinex_service import BitfinexManager


def main():
    api_key = os.getenv("BFTEST_KEY", "").strip()
    api_secret = os.getenv("BFTEST_SECRET", "").strip()
    if not api_key or not api_secret:
        print("Set BFTEST_KEY and BFTEST_SECRET (e.g. in PowerShell):")
        print('  $env:BFTEST_KEY="your_key"; $env:BFTEST_SECRET="your_secret"; python scripts/test_bitfinex_server.py')
        sys.exit(1)

    import asyncio
    mgr = BitfinexManager(api_key, api_secret)

    async def run():
        print("Testing v2/auth/r/info/user ...")
        data, err = await mgr._post("v2/auth/r/info/user", {})
        if err:
            print(f"  FAIL: {err}")
            return False
        print(f"  OK: user info = {data[:3] if isinstance(data, list) else data}")

        print("Testing v2/auth/r/wallets ...")
        data, err = await mgr._post("v2/auth/r/wallets", {})
        if err:
            print(f"  FAIL: {err}")
            return False
        print(f"  OK: wallets count = {len(data) if isinstance(data, list) else 0}")
        if isinstance(data, list):
            for w in data[:5]:
                print(f"    {w}")
        return True

    ok = asyncio.run(run())
    if ok:
        print("\nBitfinex API works. Bot should work with these keys.")
        if os.getenv("ALLOW_DEV_UPDATE") == "1":
            try:
                import requests
                api_base = os.getenv("API_BASE", "http://127.0.0.1:8000")
                r = requests.post(
                    f"{api_base}/connect-exchange/update-by-email",
                    json={
                        "email": "choiwangai@gmail.com",
                        "bfx_key": api_key,
                        "bfx_secret": api_secret,
                    },
                    timeout=15,
                )
                if r.status_code == 200:
                    print("Updated choiwangai@gmail.com vault with these keys.")
                else:
                    print(f"Update vault failed: {r.status_code} {r.text}")
            except Exception as e:
                print(f"Update vault error: {e}")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
