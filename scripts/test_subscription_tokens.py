"""
E2E test: subscription token award (Monthly Pro → +2000 purchased_tokens).

Steps:
  1. Create a test user via /dev/create-test-user.
  2. Get JWT via /dev/login-as.
  3. Create Stripe checkout session for Monthly Pro and print the URL.
  4. You complete payment in the browser (Stripe test card: 4242 4242 4242 4242).
  5. Script verifies tokens_remaining increased by 2000 (via /user-status).
  6. Prints SQL to clean up the test user.

Requires: backend running with ALLOW_DEV_CONNECT=1, STRIPE_* env set for checkout.
Run from project root:
  python scripts/test_subscription_tokens.py

Optional env:
  API_BASE  default http://127.0.0.1:8000
  OPEN_BROWSER  1 to open checkout URL in browser
"""
import os
import sys
import time

try:
    import requests
except ImportError:
    print("Install requests: pip install requests")
    sys.exit(1)

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
OPEN_BROWSER = os.getenv("OPEN_BROWSER", "").strip().lower() in ("1", "true", "yes")


def main():
    email = f"test-sub-e2e-{int(time.time())}@gmail.com"
    user_id = None

    print("1. Creating test user ...")
    r = requests.post(
        f"{API_BASE}/dev/create-test-user",
        json={"email": email},
        timeout=10,
    )
    if r.status_code != 200:
        print(f"   Failed: {r.status_code} {r.text}")
        sys.exit(1)
    data = r.json()
    user_id = data["user_id"]
    print(f"   Created user_id={user_id} email={email}")

    print("2. Getting JWT ...")
    r = requests.post(
        f"{API_BASE}/dev/login-as",
        json={"email": email},
        timeout=10,
    )
    if r.status_code != 200:
        print(f"   Failed: {r.status_code} {r.text}")
        sys.exit(1)
    token = r.json()["token"]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    print("3. Fetching initial tokens_remaining ...")
    r = requests.get(f"{API_BASE}/user-status/{user_id}", headers=headers, timeout=10)
    if r.status_code != 200:
        print(f"   Failed: {r.status_code} {r.text}")
        sys.exit(1)
    initial_tokens = r.json().get("tokens_remaining")
    if initial_tokens is None:
        initial_tokens = 0
    print(f"   Initial tokens_remaining = {initial_tokens}")

    print("4. Creating Stripe checkout session (Monthly Pro) ...")
    r = requests.post(
        f"{API_BASE}/api/create-checkout-session",
        headers=headers,
        json={"plan": "pro", "interval": "monthly"},
        timeout=10,
    )
    if r.status_code != 200:
        print(f"   Failed: {r.status_code} {r.text}")
        print("   Ensure STRIPE_API_KEY and STRIPE_PRICE_PRO_MONTHLY are set in the backend.")
        print("\nCleanup SQL (run manually if needed):")
        print(f"  DELETE FROM user_token_balance WHERE user_id = {user_id};")
        print(f"  DELETE FROM users WHERE id = {user_id};")
        sys.exit(1)
    checkout_url = r.json().get("url")
    if not checkout_url:
        print("   No URL in response.")
        sys.exit(1)
    print(f"   Checkout URL: {checkout_url}")
    if OPEN_BROWSER:
        try:
            import webbrowser
            webbrowser.open(checkout_url)
        except Exception:
            pass
    print("\n   Complete payment in the browser using Stripe test card:")
    print("   Card: 4242 4242 4242 4242  |  Expiry: any future  |  CVC: any 3 digits")
    print("   Then press Enter here to verify ...")
    input()

    print("5. Verifying tokens_remaining increased by 2000 ...")
    r = requests.get(f"{API_BASE}/user-status/{user_id}", headers=headers, timeout=10)
    if r.status_code != 200:
        print(f"   Failed: {r.status_code}")
        sys.exit(1)
    after_tokens = r.json().get("tokens_remaining")
    if after_tokens is None:
        after_tokens = 0
    diff = after_tokens - initial_tokens
    print(f"   After payment: tokens_remaining = {after_tokens} (delta = {diff})")
    if diff >= 2000:
        print("   OK: purchased_tokens increased by 2000 (or more) as expected.")
    else:
        print(f"   WARNING: expected increase of 2000, got {diff}. Check webhook and STRIPE_WEBHOOK_SECRET.")

    print("\n6. Cleanup (run in your DB):")
    print(f"  DELETE FROM user_token_balance WHERE user_id = {user_id};")
    print(f"  DELETE FROM users WHERE id = {user_id};")
    return 0


if __name__ == "__main__":
    sys.exit(main())
