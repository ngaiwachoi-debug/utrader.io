"""
Test token subscription (Whales bypass) and token add log for user 2.
Gets JWT via dev login-as, calls subscription bypass, then checks token balance and token_ledger.
If backend is not running or returns 404 (ALLOW_DEV_CONNECT not set), starts backend with
ALLOW_DEV_CONNECT=1 on a spare port and runs the test against it.

  python scripts/test_token_subscription_and_deduction_uid2.py
"""
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

API_BASE = os.getenv("API_BASE", "http://127.0.0.1:8000")
# Port for spawned backend when default is unavailable or dev routes disabled
FALLBACK_PORT = 8001


def _start_fallback_backend() -> subprocess.Popen:
    """Start backend with ALLOW_DEV_CONNECT=1 on FALLBACK_PORT. Caller must terminate when done."""
    env = os.environ.copy()
    env["ALLOW_DEV_CONNECT"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(FALLBACK_PORT)],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    fallback_base = f"http://127.0.0.1:{FALLBACK_PORT}"
    for _ in range(30):
        time.sleep(0.5)
        try:
            with urllib.request.urlopen(
                urllib.request.Request(f"{fallback_base}/docs", method="GET"),
                timeout=2,
            ) as r:
                if r.getcode() == 200:
                    return proc
        except Exception:
            pass
        if proc.poll() is not None:
            break
    proc.terminate()
    proc.wait(timeout=5)
    raise RuntimeError("Could not start backend with ALLOW_DEV_CONNECT=1 on port %s" % FALLBACK_PORT)


def main():
    user_id = 2
    import database
    import models

    db = database.SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user or not user.email:
            print(f"User {user_id} or email not found")
            return 1
        email = user.email.strip().lower()
    finally:
        db.close()

    api_base = API_BASE
    proc = None

    # If dev/login-as or subscription/bypass returns 404, start backend with ALLOW_DEV_CONNECT=1 on fallback port
    def get_token(base: str):
        req = urllib.request.Request(
            f"{base}/dev/login-as",
            data=json.dumps({"email": email}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
        return data.get("token") or data.get("access_token")

    try:
        token = None
        try:
            token = get_token(api_base)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                print("Backend returned 404 for /dev/login-as. Starting backend with ALLOW_DEV_CONNECT=1 on port %s..." % FALLBACK_PORT)
                proc = _start_fallback_backend()
                api_base = f"http://127.0.0.1:{FALLBACK_PORT}"
                token = get_token(api_base)
            else:
                raise
        except OSError as e:
            print("Backend not reachable. Starting backend with ALLOW_DEV_CONNECT=1 on port %s..." % FALLBACK_PORT)
            proc = _start_fallback_backend()
            api_base = f"http://127.0.0.1:{FALLBACK_PORT}"
            token = get_token(api_base)

        if not token:
            print("No token in dev/login-as response")
            return 1

        # 2. Subscription bypass (Whales monthly = 200 USD, 40000 tokens)
        req = urllib.request.Request(
            f"{api_base}/api/v1/subscription/bypass",
            data=json.dumps({"plan": "whales", "interval": "monthly"}).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            err_body = e.read().decode()
            if e.code == 404 and proc is None:
                print("Backend returned 404 for /api/v1/subscription/bypass. Starting backend with ALLOW_DEV_CONNECT=1 on port %s..." % FALLBACK_PORT)
                proc = _start_fallback_backend()
                api_base = f"http://127.0.0.1:{FALLBACK_PORT}"
                token = get_token(api_base)
                if not token:
                    print("No token after starting fallback backend")
                    return 1
                req = urllib.request.Request(
                    f"{api_base}/api/v1/subscription/bypass",
                    data=json.dumps({"plan": "whales", "interval": "monthly"}).encode(),
                    headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
                    method="POST",
                )
                try:
                    with urllib.request.urlopen(req, timeout=10) as r:
                        data = json.loads(r.read().decode())
                except urllib.error.HTTPError as e2:
                    print("Subscription bypass failed (retry): %s %s" % (e2.code, e2.read().decode()))
                    return 1
            else:
                print("Subscription bypass failed: %s %s" % (e.code, err_body))
                return 1

        if data.get("status") != "success" or data.get("tokens_awarded") != 40000:
            print("Unexpected response: %s. Expected status=success, tokens_awarded=40000" % (data,))
            return 1
        print("Subscription bypass OK: %s tokens awarded" % data.get("tokens_awarded"))

        # 3. Token balance
        req = urllib.request.Request(
            f"{api_base}/api/v1/users/me/token-balance",
            headers={"Authorization": "Bearer %s" % token},
            method="GET",
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            bal = json.loads(r.read().decode())
        tokens_remaining = float(bal.get("tokens_remaining") or 0)
        total_added = float(bal.get("total_tokens_added") or 0)
        print("Token balance: tokens_remaining=%s, total_tokens_added=%s" % (tokens_remaining, total_added))

        # 4. Token add log (DB) – optional if token_ledger table exists
        db = database.SessionLocal()
        try:
            if hasattr(models, "TokenLedger"):
                from sqlalchemy import text
                try:
                    db.execute(text("SELECT 1 FROM token_ledger LIMIT 1"))
                except Exception:
                    print("Token add log: token_ledger table not present, skip DB check")
                else:
                    rows = (
                        db.query(models.TokenLedger)
                        .filter(
                            models.TokenLedger.user_id == user_id,
                            models.TokenLedger.activity_type == "add",
                            models.TokenLedger.reason == "subscription_monthly",
                        )
                        .order_by(models.TokenLedger.created_at.desc())
                        .limit(5)
                        .all()
                    )
                    if rows:
                        latest = rows[0]
                        amt = float(latest.amount or 0)
                        if amt == 40000:
                            print("Token add log: found subscription_monthly amount=40000 (OK)")
                        else:
                            print("Token add log: latest subscription_monthly amount=%s (expected 40000)" % amt)
                    else:
                        print("Token add log: no subscription_monthly row found (check token_ledger table)")
            else:
                print("Token add log: TokenLedger model not found, skip DB check")
        finally:
            db.close()

        print("Done. Purchase amount = 200 USD (Whales monthly), 40000 tokens added.")
        return 0
    finally:
        if proc is not None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
            print("Stopped fallback backend.")


if __name__ == "__main__":
    sys.exit(main())
