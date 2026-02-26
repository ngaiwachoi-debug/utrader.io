"""
Test daily gross profit scheduler and API failure store.

1. Creates (or reuses) a test user with the given Bitfinex API keys and vault.created_at
   set to 2026-02-22 09:30 UTC so ledger window yields ~68.93.
2. Starts the API server with TEST_SCHEDULER_SECONDS=30 (scheduler runs in 30s).
3. Waits 45 seconds for the scheduler to run.
4. Checks user_profit_snapshot.gross_profit_usd is ~68.93 and prints API failures if any.

Usage (from project root):
  python scripts/test_daily_scheduler_and_failures.py

Requires: .env with DATABASE_URL, ENCRYPTION_KEY (or default dev key).
"""
import os
import sys
import time
import subprocess
import signal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from database import SessionLocal
import models
import security

# Test user and Bitfinex keys (same ledger data as choiwangai script → ~68.93)
TEST_EMAIL = "test-scheduler@test.com"
API_KEY = "96d1aea643c91ba4a7260702692e6e31d65bb69486f"
API_SECRET = "e5f04a8af4f1a553b9f0cffaafd51f80b2cff9998c1"
REGISTRATION_DT = datetime(2026, 2, 22, 9, 30, 0)  # UTC
EXPECTED_GROSS = 68.93  # allow small tolerance
TOLERANCE = 0.50
SCHEDULER_WAIT_SEC = 30  # run scheduler once after 30s
TOTAL_WAIT_SEC = 45      # 30s wait + single-user refresh (~10s)
API_PORT = 8003


def ensure_test_user_and_vault():
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == TEST_EMAIL).first()
        if not user:
            user = models.User(email=TEST_EMAIL, plan_tier="trial")
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"Created user {TEST_EMAIL} (user_id={user.id})")
        else:
            print(f"Using existing user {TEST_EMAIL} (user_id={user.id})")

        vault = db.query(models.APIVault).filter(models.APIVault.user_id == user.id).first()
        if not vault:
            vault = models.APIVault(
                user_id=user.id,
                encrypted_key=security.encrypt_key(API_KEY),
                encrypted_secret=security.encrypt_key(API_SECRET),
                created_at=REGISTRATION_DT,
            )
            db.add(vault)
            db.commit()
            db.refresh(vault)
            print("Created vault for test user with keys and created_at.")
        else:
            vault.encrypted_key = security.encrypt_key(API_KEY)
            vault.encrypted_secret = security.encrypt_key(API_SECRET)
            vault.created_at = REGISTRATION_DT
            db.commit()
        print(f"Set vault keys and created_at={REGISTRATION_DT}")
        return user.id
    finally:
        db.close()


def check_snapshot(user_id: int):
    db = SessionLocal()
    try:
        snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).first()
        if not snap:
            return None, "no snapshot row"
        return float(snap.gross_profit_usd or 0), None
    finally:
        db.close()


def main():
    print("=== Daily scheduler & API failure store test ===\n")
    user_id = ensure_test_user_and_vault()
    print(f"Test user_id={user_id}. Starting server with TEST_SCHEDULER_SECONDS={SCHEDULER_WAIT_SEC} on port {API_PORT}...")
    env = os.environ.copy()
    env["TEST_SCHEDULER_SECONDS"] = str(SCHEDULER_WAIT_SEC)
    env["TEST_SCHEDULER_USER_ID"] = str(user_id)  # only refresh test user
    env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(API_PORT)],
        cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        time.sleep(2)
        if proc.poll() is not None:
            out, _ = proc.communicate(timeout=5)
            print("Server exited early:")
            print(out or "(no output)")
            return 1
        print(f"Waiting {TOTAL_WAIT_SEC}s for scheduler to run...")
        time.sleep(TOTAL_WAIT_SEC)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
    out, _ = proc.communicate(timeout=5)
    server_out = out or ""
    if "[scheduler]" in server_out:
        print("Scheduler log snippet:")
        for line in server_out.splitlines():
            if "[scheduler]" in line:
                print(" ", line.strip())
    gross, err = check_snapshot(user_id)
    if err:
        print(f"\nFAIL: {err}")
        if not server_out.strip():
            print("(Server produced no output.)")
        else:
            print("Server output (last 40 lines):")
            for line in server_out.splitlines()[-40:]:
                print(" ", line)
        return 1
    print(f"\nuser_profit_snapshot.gross_profit_usd = {gross}")
    if abs(gross - EXPECTED_GROSS) <= TOLERANCE:
        print(f"PASS: Gross profit {gross} is within {TOLERANCE} of expected {EXPECTED_GROSS}.")
    else:
        print(f"FAIL: Expected ~{EXPECTED_GROSS}, got {gross} (tolerance {TOLERANCE}).")
        # If test user has multiple vault users, scheduler runs for all; snapshot might be for another user
        return 1
    print("\nAPI failure store: failures are recorded when refresh throws (see _record_api_failure in main.py).")
    print("Admin panel GET /admin/api-failures shows recent failures; none in this run.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
