#!/usr/bin/env python3
"""
E2E test: 3-tier referral rewards on purchase (L1=10%, L2=5%, L3=2% of USD).
Chain A -> B -> C -> D. D deposits 50,000 USD (5M tokens), then admin adds D 50,000 USD (5M tokens).
Expected: L1 (C) = 5000 + 5000 = 10000, L2 (B) = 2500 + 2500 = 5000, L3 (A) = 1000 + 1000 = 2000 USDT credit.

Requires: ALLOW_DEV_CONNECT=1, backend running (restart backend after pulling referral-on-purchase changes).
Optional: ADMIN_TOKEN env for bulk-add and listing usdt_credit. Delete endpoint requires latest backend.
Usage: python scripts/test_referral_purchase_rewards.py
"""
import os
import sys

try:
    import requests
except ImportError:
    print("pip install requests")
    sys.exit(1)

BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
ADMIN_TOKEN = os.getenv("ADMIN_TOKEN", "")

EMAIL_A = "ref_test_a@gmail.com"
EMAIL_B = "ref_test_b@gmail.com"
EMAIL_C = "ref_test_c@gmail.com"
EMAIL_D = "ref_test_d@gmail.com"

USD_50K = 50_000.0
TOKENS_50K = 5_000_000  # 1 USD = 100 tokens


def create_user(email: str, referral_code: str | None = None) -> dict:
    body = {"email": email}
    if referral_code:
        body["referral_code"] = referral_code
    r = requests.post(f"{BASE}/dev/create-test-user", json=body, timeout=10)
    r.raise_for_status()
    return r.json()


def login_as(email: str) -> str:
    r = requests.post(f"{BASE}/dev/login-as", json={"email": email}, timeout=10)
    r.raise_for_status()
    return r.json()["token"]


def deposit_bypass(user_token: str, usd_amount: float) -> dict:
    r = requests.post(
        f"{BASE}/api/v1/tokens/deposit",
        json={"usd_amount": usd_amount, "bypass_payment": True},
        headers={"Authorization": f"Bearer {user_token}"},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def admin_bulk_add(admin_token: str, user_id: int, tokens: int) -> dict:
    r = requests.post(
        f"{BASE}/admin/tokens/bulk-add",
        json={"items": [{"user_id": user_id, "amount": tokens}]},
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def admin_list_usdt_credit(admin_token: str) -> list:
    r = requests.get(
        f"{BASE}/admin/usdt-credit",
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=10,
    )
    r.raise_for_status()
    return r.json()


def delete_user(email: str) -> dict:
    r = requests.delete(f"{BASE}/dev/users/by-email", params={"email": email}, timeout=10)
    r.raise_for_status()
    return r.json()


def main():
    print("=== 3-Tier Referral Purchase Rewards E2E ===\n")
    print("Chain: A -> B -> C -> D")
    print("D deposits 50,000 USD (5M tokens); then admin adds D 50,000 USD (5M tokens).")
    print("Expected: L1(C)=10000, L2(B)=5000, L3(A)=2000 USDT credit.\n")

    ids = {}
    codes = {}

    # 1. Create A, B, C, D with referral chain
    print("1. Creating users A, B, C, D with chain A->B->C->D ...")
    a = create_user(EMAIL_A)
    ids["A"] = a["user_id"]
    codes["A"] = (a.get("referral_code") or "").strip()
    if not codes["A"]:
        print("   WARNING: A has no referral_code (restart backend to get create-test-user referral_code). Chain may be broken.")
    print(f"   A: user_id={ids['A']} referral_code={codes['A'] or '(empty)'}")

    b = create_user(EMAIL_B, codes["A"])
    ids["B"] = b["user_id"]
    codes["B"] = b.get("referral_code") or ""
    print(f"   B: user_id={ids['B']} referral_code={codes['B']}")

    c = create_user(EMAIL_C, codes["B"])
    ids["C"] = c["user_id"]
    codes["C"] = c.get("referral_code") or ""
    print(f"   C: user_id={ids['C']} referral_code={codes['C']}")

    d = create_user(EMAIL_D, codes["C"])
    ids["D"] = d["user_id"]
    print(f"   D: user_id={ids['D']}")

    # 2. D deposits 50,000 USD (bypass)
    print("\n2. D deposits 50,000 USD (bypass) ...")
    token_d = login_as(EMAIL_D)
    dep = deposit_bypass(token_d, USD_50K)
    print(f"   {dep.get('message', dep)}")

    # 3. Admin bulk add D 5M tokens (50k USD) if ADMIN_TOKEN set
    if ADMIN_TOKEN:
        print("\n3. Admin bulk add D 5,000,000 tokens (50k USD) ...")
        bulk = admin_bulk_add(ADMIN_TOKEN, ids["D"], TOKENS_50K)
        print(f"   success_count={bulk.get('success_count')} failed_count={bulk.get('failed_count')}")
    else:
        print("\n3. Skipping admin bulk add (set ADMIN_TOKEN to run).")

    # 4. Show user_usdt_credit for A, B, C, D
    print("\n4. user_usdt_credit table (test users):")
    email_to_label = {EMAIL_A: "A", EMAIL_B: "B", EMAIL_C: "C", EMAIL_D: "D"}
    if ADMIN_TOKEN:
        rows = admin_list_usdt_credit(ADMIN_TOKEN)
        test_rows = [row for row in rows if row.get("email") in (EMAIL_A, EMAIL_B, EMAIL_C, EMAIL_D)]
        for row in test_rows:
            label = email_to_label.get(row["email"], "?")
            print(f"   {label} (user_id={row['user_id']} email={row['email']}): "
                  f"usdt_credit={row.get('usdt_credit', 0)} total_earned={row.get('total_earned', 0)} "
                  f"total_withdrawn={row.get('total_withdrawn', 0)}")
        if not test_rows:
            print("   (no rows found - check admin usdt-credit endpoint)")
    else:
        print("   Set ADMIN_TOKEN to list from API, or query DB: SELECT * FROM user_usdt_credit WHERE user_id IN (...);")

    # 5. Remove test users
    print("\n5. Removing test users ...")
    for email in (EMAIL_D, EMAIL_C, EMAIL_B, EMAIL_A):
        try:
            out = delete_user(email)
            print(f"   {email}: deleted={out.get('deleted', False)}")
        except Exception as e:
            print(f"   {email}: error {e}")

    print("\nDone.")


if __name__ == "__main__":
    main()
