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
# Use these or set env BFX_KEY, BFX_SECRET, GEMINI_KEY
API_KEY = os.getenv("BFX_KEY", "96d1aea643c91ba4a7260702692e6e31d65bb69486f")
API_SECRET = os.getenv("BFX_SECRET", "e5f04a8af4f1a553b9f0cffaafd51f80b2cff9998c1")
GEMINI_KEY = os.getenv("GEMINI_KEY", "AIzaSyAm0fmzCZPlFrHBej4CVDoPKZNXQ11BijU")

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
URL_UPDATE = f"{API_BASE}/connect-exchange/update-by-email"
URL_CONNECT = f"{API_BASE}/connect-exchange/by-email"


def main():
    print(f"Connecting to {API_BASE} ...")
    print(f"Saving API keys for {EMAIL} ...")
    payload = {"email": EMAIL, "bfx_key": API_KEY, "bfx_secret": API_SECRET}
    if GEMINI_KEY:
        payload["gemini_key"] = GEMINI_KEY
    # Prefer update-by-email (works when user already used trial); fallback to by-email for new users
    for url, label in [(URL_UPDATE, "update"), (URL_CONNECT, "connect")]:
        try:
            r = requests.post(url, json=payload, timeout=30)
        except requests.exceptions.ConnectionError as e:
            print(f"Connection error: {e}")
            print("Make sure the backend is running (e.g. uvicorn main:app) and ALLOW_DEV_CONNECT=1 in .env")
            sys.exit(1)
        if r.status_code == 404 and label == "update":
            continue
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
        break
    else:
        print("Backend returned 404. Set ALLOW_DEV_CONNECT=1 in the backend .env file.")
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
