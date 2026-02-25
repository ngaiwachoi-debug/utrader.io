"""
Save Bitfinex API keys for choiwangai@gmail.com via the backend.
Requires: backend running (e.g. uvicorn main:app), ALLOW_DEV_CONNECT=1 in backend .env.

Usage (from project root):
  python scripts/save_api_keys_for_user.py

Or with custom API base:
  API_BASE=http://127.0.0.1:8000 python scripts/save_api_keys_for_user.py
"""
import os
import sys

try:
    import requests
except ImportError:
    print("Install requests: pip install requests")
    sys.exit(1)

EMAIL = "choiwangai@gmail.com"
API_KEY = "4b7e10b7478dbd2de2b8a402cf155e0dfd47685292f"
API_SECRET = "3be479ee822ee34054d5587861bf3f3c2f14f33ecf3"

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
URL = f"{API_BASE}/connect-exchange/by-email"


def main():
    print(f"Connecting to {API_BASE} ...")
    print(f"Saving API keys for {EMAIL} ...")
    try:
        r = requests.post(
            URL,
            json={
                "email": EMAIL,
                "bfx_key": API_KEY,
                "bfx_secret": API_SECRET,
            },
            timeout=30,
        )
    except requests.exceptions.ConnectionError as e:
        print(f"Connection error: {e}")
        print("Make sure the backend is running (e.g. uvicorn main:app) and ALLOW_DEV_CONNECT=1 in .env")
        sys.exit(1)

    if r.status_code == 404:
        print("Backend returned 404. Set ALLOW_DEV_CONNECT=1 in the backend .env file.")
        sys.exit(1)
    if r.status_code != 200:
        try:
            detail = r.json().get("detail", r.text)
        except Exception:
            detail = r.text
        print(f"Error {r.status_code}: {detail}")
        sys.exit(1)

    data = r.json()
    balance = data.get("balance") or {}
    total = balance.get("total_usd_all")
    print("Success! API keys saved for", EMAIL)
    if total is not None:
        print(f"Funding wallet (total USD): ${float(total):,.2f}")
    print("You can now log in as", EMAIL, "and see Current Configuration in Settings.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
