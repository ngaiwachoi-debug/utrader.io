"""
Test Live Status data for user id 2: dashboard-fold and wallets/2.
Requires: backend running, .env with NEXTAUTH_SECRET and DATABASE_URL.
Run from project root: python scripts/test_live_status_uid2.py
"""
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from dotenv import load_dotenv
load_dotenv()

try:
    import requests
except ImportError:
    print("pip install requests")
    sys.exit(1)
try:
    import jwt
except ImportError:
    print("pip install PyJWT")
    sys.exit(1)

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
USER_ID = 2


def main():
    from database import SessionLocal
    import models

    secret = os.getenv("NEXTAUTH_SECRET")
    if not secret:
        print("NEXTAUTH_SECRET not set in .env")
        return 1

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.id == USER_ID).first()
        if not user:
            print(f"User id {USER_ID} not found in DB.")
            return 1
        email = (user.email or "").strip()
        if not email:
            print(f"User id {USER_ID} has no email.")
            return 1
        vault = getattr(user, "vault", None)
        if not vault:
            print(f"User id {USER_ID} has no API keys (vault). Live Status needs Bitfinex keys.")
    finally:
        db.close()

    now = int(time.time())
    token = jwt.encode(
        {"email": email, "sub": str(USER_ID), "iat": now, "exp": now + 3600},
        secret,
        algorithm="HS256",
    )
    if hasattr(token, "decode"):
        token = token.decode("utf-8")
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    passed = 0
    failed = 0
    problems = []

    def ok(msg):
        nonlocal passed
        print(f"  [PASS] {msg}")
        passed += 1

    def fail(msg, detail=""):
        nonlocal failed
        print(f"  [FAIL] {msg}" + (f" — {detail}" if detail else ""))
        failed += 1
        problems.append(f"{msg}: {detail}" if detail else msg)

    print("--- Live Status test (user_id=2) ---")
    print(f"API_BASE={API_BASE}  USER_ID={USER_ID}  email={email}  has_vault={bool(vault)}")
    print()

    # 1. GET /api/dashboard-fold as user 2
    try:
        r = requests.get(f"{API_BASE}/api/dashboard-fold", headers=headers, timeout=25)
        if r.status_code != 200:
            fail("GET /api/dashboard-fold", f"status={r.status_code} body={r.text[:200]}")
        else:
            ok("GET /api/dashboard-fold returns 200")
            data = r.json()
            for key in ("wallets", "botStats", "userStatus", "lending"):
                if key not in data:
                    fail(f"dashboard-fold missing key: {key}")
                else:
                    ok(f"dashboard-fold has {key}")

            wallets = data.get("wallets") or {}
            if isinstance(wallets, dict):
                total = wallets.get("total_usd_all")
                if total is None and "message" not in wallets:
                    fail("wallets missing total_usd_all")
                else:
                    ok("wallets has expected shape")
                if total == 0 and vault:
                    problems.append("Wallets total_usd_all is 0 despite user having vault (Bitfinex snapshot may be failing or keys empty).")
            else:
                fail("wallets is not a dict", str(type(wallets)))
    except requests.exceptions.ConnectionError:
        fail("GET /api/dashboard-fold", "Connection refused — is the backend running?")
    except Exception as e:
        fail("GET /api/dashboard-fold", str(e))

    # 2. GET /wallets/2 as user 2
    try:
        r = requests.get(f"{API_BASE}/wallets/{USER_ID}", headers=headers, timeout=25)
        if r.status_code == 503:
            fail("GET /wallets/2", "503 Service Unavailable (should be 200 with X-Data-Incomplete when incomplete)")
        elif r.status_code != 200:
            fail("GET /wallets/2", f"status={r.status_code} body={r.text[:200]}")
        else:
            ok("GET /wallets/2 returns 200")
            data = r.json()
            incomplete = r.headers.get("X-Data-Incomplete") == "true"
            if incomplete:
                problems.append("wallets/2 returned X-Data-Incomplete: true (Bitfinex snapshot incomplete; check Redis/Bitfinex).")
            if isinstance(data, dict) and "total_usd_all" in data:
                ok("wallets/2 has total_usd_all")
            else:
                fail("wallets/2 response shape", str(data)[:150])
    except requests.exceptions.ConnectionError:
        fail("GET /wallets/2", "Connection refused")
    except Exception as e:
        fail("GET /wallets/2", str(e))

    # 3. GET /bot-stats/2
    try:
        r = requests.get(f"{API_BASE}/bot-stats/{USER_ID}", headers=headers, timeout=10)
        if r.status_code != 200:
            fail("GET /bot-stats/2", f"status={r.status_code}")
        else:
            ok("GET /bot-stats/2 returns 200")
    except Exception as e:
        fail("GET /bot-stats/2", str(e))

    print()
    if problems:
        print("Potential problems:")
        for p in problems:
            print(f"  - {p}")
        print()
    print(f"Result: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
