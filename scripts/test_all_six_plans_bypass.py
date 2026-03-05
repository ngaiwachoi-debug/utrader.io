"""
Fully automated test of all 6 subscription plans via /api/v1/subscription/bypass (no Stripe/browser).

For each (plan, interval): calls bypass, then verifies token balance increased by expected amount.
Requires: backend running with ALLOW_DEV_CONNECT=1.
Run from project root: python scripts/test_all_six_plans_bypass.py [--user 2]

If the backend is not running, use: python scripts/test_all_six_plans_inprocess.py [--user 2]
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


def get_jwt(user_id: int) -> str:
    r = requests.post(
        f"{API_BASE}/dev/jwt-for-user",
        json={"user_id": user_id},
        timeout=30,
    )
    if r.status_code != 200:
        print(f"FAIL: JWT for user_id={user_id}: {r.status_code} {r.text}")
        sys.exit(1)
    return r.json()["token"]


def get_token_balance(user_id: int, headers: dict) -> float:
    r = requests.get(f"{API_BASE}/user-status/{user_id}", headers=headers, timeout=30)
    if r.status_code != 200:
        print(f"FAIL: user-status: {r.status_code} {r.text}")
        sys.exit(1)
    return float(r.json().get("tokens_remaining") or 0)


def call_bypass(plan: str, interval: str, headers: dict) -> None:
    r = requests.post(
        f"{API_BASE}/api/v1/subscription/bypass",
        headers=headers,
        json={"plan": plan, "interval": interval},
        timeout=30,
    )
    if r.status_code != 200:
        raise RuntimeError(f"bypass {r.status_code} {r.text}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", type=int, default=2, help="User ID (default 2)")
    args = parser.parse_args()
    user_id = args.user

    print(f"API_BASE={API_BASE} user_id={user_id}")
    print("Getting JWT ...")
    token = get_jwt(user_id)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    balance = get_token_balance(user_id, headers)
    print(f"Initial tokens_remaining = {balance}\n")

    failed = []
    for plan in PLANS:
        for interval in INTERVALS:
            key = (plan, interval)
            expected = EXPECTED_TOKENS[key]
            try:
                call_bypass(plan, interval, headers)
            except Exception as e:
                print(f"  {plan} {interval}: FAIL bypass - {e}")
                failed.append((plan, interval, str(e)))
                continue
            new_balance = get_token_balance(user_id, headers)
            delta = new_balance - balance
            if delta == expected:
                print(f"  {plan} {interval}: OK (+{expected})")
            else:
                print(f"  {plan} {interval}: FAIL expected +{expected}, got +{delta} (balance {balance} -> {new_balance})")
                failed.append((plan, interval, f"expected +{expected}, got +{delta}"))
            balance = new_balance

    print()
    if failed:
        print(f"FAILED: {len(failed)}/6 plans")
        for plan, interval, msg in failed:
            print(f"  {plan} {interval}: {msg}")
        sys.exit(1)
    print("PASSED: all 6 plans.")
    sys.exit(0)


if __name__ == "__main__":
    main()
