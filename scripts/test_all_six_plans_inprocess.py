"""
Fully automated test of all 6 subscription plans using FastAPI TestClient (no HTTP server needed).

Sets ALLOW_DEV_CONNECT=1, then calls /dev/jwt-for-user and /api/v1/subscription/bypass in-process.
Requires: .env with DB etc. Run from project root: python scripts/test_all_six_plans_inprocess.py [--user 2]
"""
import argparse
import os
import sys

# Set before any main import so dev routes are enabled
os.environ["ALLOW_DEV_CONNECT"] = "1"

# Project root
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _root not in sys.path:
    sys.path.insert(0, _root)
os.chdir(_root)

try:
    from fastapi.testclient import TestClient
    from main import app
except Exception as e:
    print(f"Import failed: {e}")
    sys.exit(1)

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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", type=int, default=2, help="User ID (default 2)")
    args = parser.parse_args()
    user_id = args.user

    client = TestClient(app)

    print(f"user_id={user_id} (in-process test)")
    r = client.post("/dev/jwt-for-user", json={"user_id": user_id})
    if r.status_code != 200:
        print(f"FAIL: JWT: {r.status_code} {r.text}")
        sys.exit(1)
    token = r.json()["token"]
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    r = client.get(f"/user-status/{user_id}", headers=headers)
    if r.status_code != 200:
        print(f"FAIL: user-status: {r.status_code} {r.text}")
        sys.exit(1)
    balance = float(r.json().get("tokens_remaining") or 0)
    print(f"Initial tokens_remaining = {balance}\n")

    failed = []
    for plan in PLANS:
        for interval in INTERVALS:
            key = (plan, interval)
            expected = EXPECTED_TOKENS[key]
            r = client.post(
                "/api/v1/subscription/bypass",
                headers=headers,
                json={"plan": plan, "interval": interval},
            )
            if r.status_code != 200:
                print(f"  {plan} {interval}: FAIL bypass {r.status_code} {r.text}")
                failed.append((plan, interval, f"bypass {r.status_code}"))
                continue
            r = client.get(f"/user-status/{user_id}", headers=headers)
            if r.status_code != 200:
                print(f"  {plan} {interval}: FAIL user-status {r.status_code}")
                failed.append((plan, interval, "user-status fail"))
                continue
            new_balance = float(r.json().get("tokens_remaining") or 0)
            delta = new_balance - balance
            if delta == expected:
                print(f"  {plan} {interval}: OK (+{expected})")
            else:
                print(f"  {plan} {interval}: FAIL expected +{expected}, got +{delta}")
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
