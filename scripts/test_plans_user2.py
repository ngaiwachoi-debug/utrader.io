"""
Test all 6 subscription plans for a given user (default: user_id=2) via UI flow.

For each plan (Pro/AI Ultra/Whales x Monthly/Yearly):
  1. Create Stripe Checkout session and print/open URL.
  2. You complete payment in the browser (Stripe test card: 4242 4242 4242 4242).
  3. Press Enter; script verifies token balance increased by the expected amount.

Requires: backend running with ALLOW_DEV_CONNECT=1, STRIPE_* env set.
Run from project root:
  python scripts/test_plans_user2.py
  python scripts/test_plans_user2.py --user 2
  python scripts/test_plans_user2.py --plan pro --interval monthly   # single plan

Optional env:
  API_BASE          default http://127.0.0.1:8000
  OPEN_BROWSER=1     open checkout URL in browser after each step
"""
import argparse
import os
import sys

try:
    import requests
except ImportError:
    print("Install requests: pip install requests")
    sys.exit(1)

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
OPEN_BROWSER = os.getenv("OPEN_BROWSER", "").strip().lower() in ("1", "true", "yes")

# Expected token award per plan/interval (must match backend PLAN_TOKEN_AWARD_*)
EXPECTED_TOKENS = {
    ("pro", "monthly"): 2000,
    ("pro", "yearly"): 24000,
    ("ai_ultra", "monthly"): 9000,
    ("ai_ultra", "yearly"): 108000,
    ("whales", "monthly"): 40000,
    ("whales", "yearly"): 480000,
}

PLANS = ["pro", "ai_ultra", "whales"]
INTERVALS = ["monthly", "yearly"]


def get_jwt(user_id: int, email: str | None = None) -> str:
    if email:
        r = requests.post(
            f"{API_BASE}/dev/login-as",
            json={"email": email},
            timeout=10,
        )
        if r.status_code != 200:
            print(f"Failed to get JWT for email={email}: {r.status_code} {r.text}")
            sys.exit(1)
        return r.json()["token"]
    r = requests.post(
        f"{API_BASE}/dev/jwt-for-user",
        json={"user_id": user_id},
        timeout=10,
    )
    if r.status_code != 200:
        print(f"Failed to get JWT for user_id={user_id}: {r.status_code} {r.text}")
        print("Tip: set ALLOW_DEV_CONNECT=1 and restart backend, or pass --email <user2@example.com>")
        sys.exit(1)
    return r.json()["token"]


def get_token_balance(user_id: int, headers: dict) -> float:
    r = requests.get(f"{API_BASE}/user-status/{user_id}", headers=headers, timeout=10)
    if r.status_code != 200:
        print(f"Failed to get token balance: {r.status_code} {r.text}")
        return 0.0
    return float(r.json().get("tokens_remaining") or 0)


def create_checkout(user_id: int, plan: str, interval: str, headers: dict) -> str:
    r = requests.post(
        f"{API_BASE}/api/create-checkout-session",
        headers=headers,
        json={"plan": plan, "interval": interval},
        timeout=10,
    )
    if r.status_code != 200:
        raise RuntimeError(f"{r.status_code} {r.text}")
    data = r.json()
    url = data.get("url")
    if not url:
        raise RuntimeError("No URL in response")
    return url


def main():
    parser = argparse.ArgumentParser(description="Test subscription plans for a user (default: 2)")
    parser.add_argument("--user", type=int, default=2, help="User ID to test (default: 2)")
    parser.add_argument("--plan", choices=PLANS, help="Test only this plan")
    parser.add_argument("--interval", choices=INTERVALS, help="Test only this interval")
    parser.add_argument("--no-verify", action="store_true", help="Skip balance verification after payment")
    parser.add_argument("--dry-run", action="store_true", help="Only create checkout URLs for each plan (no payment, no verify)")
    parser.add_argument("--email", type=str, help="Use /dev/login-as with this email instead of /dev/jwt-for-user (e.g. for user 2)")
    args = parser.parse_args()

    user_id = args.user
    plans_to_test = [args.plan] if args.plan else PLANS
    intervals_to_test = [args.interval] if args.interval else INTERVALS

    print(f"Getting JWT for user_id={user_id}" + (f" (email={args.email})" if args.email else "") + " ...")
    token = get_jwt(user_id, args.email)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    initial_balance = get_token_balance(user_id, headers)
    print(f"Initial tokens_remaining = {initial_balance}\n")

    for plan in plans_to_test:
        for interval in intervals_to_test:
            key = (plan, interval)
            expected = EXPECTED_TOKENS.get(key, 0)
            print(f"--- {plan} {interval} (expected +{expected} tokens) ---")
            try:
                url = create_checkout(user_id, plan, interval, headers)
                print(f"Checkout URL: {url}")
                if OPEN_BROWSER and not args.dry_run:
                    try:
                        import webbrowser
                        webbrowser.open(url)
                    except Exception:
                        pass
            except Exception as e:
                print(f"FAIL: {e}")
                continue
            if args.dry_run:
                print("(dry-run: skip payment)")
                continue
            print("Complete payment in the browser (test card: 4242 4242 4242 4242), then press Enter here ...")
            input()

            if not args.no_verify:
                after = get_token_balance(user_id, headers)
                diff = after - initial_balance
                if diff >= expected:
                    print(f"OK: tokens_remaining = {after} (delta = {diff}, expected >= {expected})")
                else:
                    print(f"WARNING: tokens_remaining = {after} (delta = {diff}, expected >= {expected}). Check webhook.")
                initial_balance = after
            print()

    print("Done.")


if __name__ == "__main__":
    main()
