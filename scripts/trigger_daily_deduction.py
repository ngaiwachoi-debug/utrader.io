#!/usr/bin/env python3
"""
Trigger daily token deduction via API (same as Admin Panel → Deduction → Manual trigger).

Requires:
- Backend running (e.g. uvicorn main:app).
- ALLOW_DEV_CONNECT=1 in backend .env so /dev/login-as is available.
- ADMIN_EMAIL (or default ngaiwachoi@gmail.com) must be an existing user in the DB.

Usage:
  python scripts/trigger_daily_deduction.py
  ADMIN_EMAIL=other@example.com python scripts/trigger_daily_deduction.py
  API_BASE=https://your-api.example.com python scripts/trigger_daily_deduction.py
"""
import os
import sys

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000").rstrip("/")
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "ngaiwachoi@gmail.com").strip().lower()


def main():
    try:
        import requests
    except ImportError:
        print("Install requests: pip install requests", file=sys.stderr)
        sys.exit(1)

    # Get admin JWT via dev login (requires ALLOW_DEV_CONNECT=1)
    login_url = f"{API_BASE}/dev/login-as"
    r = requests.post(login_url, json={"email": ADMIN_EMAIL}, timeout=10)
    if r.status_code == 404:
        print("Backend returned 404 for /dev/login-as. Set ALLOW_DEV_CONNECT=1 in backend .env and restart.", file=sys.stderr)
        sys.exit(1)
    if r.status_code != 200:
        print(f"Login failed: {r.status_code} {r.text[:200]}", file=sys.stderr)
        sys.exit(1)
    try:
        token = r.json()["token"]
    except (KeyError, ValueError):
        print("Invalid login response:", r.text[:200], file=sys.stderr)
        sys.exit(1)

    # Run deduction with refresh (same as Manual trigger with refresh_first=true)
    trigger_url = f"{API_BASE}/admin/deduction/trigger?refresh_first=true"
    r2 = requests.post(trigger_url, headers={"Authorization": f"Bearer {token}"}, timeout=300)
    if r2.status_code != 200:
        print(f"Deduction trigger failed: {r2.status_code} {r2.text[:500]}", file=sys.stderr)
        sys.exit(1)
    out = r2.json()
    print("Deduction run succeeded.")
    print(f"  status: {out.get('status')}")
    print(f"  count: {out.get('count', 0)}")
    print(f"  refreshed: {out.get('refreshed', 0)}")
    if out.get("entries"):
        for e in out["entries"][:10]:
            print(f"  - user_id={e.get('user_id')} gross_profit={e.get('gross_profit')} tokens_deducted={e.get('tokens_deducted')}")
        if len(out["entries"]) > 10:
            print(f"  ... and {len(out['entries']) - 10} more")
    return 0


if __name__ == "__main__":
    sys.exit(main())
