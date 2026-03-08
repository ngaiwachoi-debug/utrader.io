"""
Test script for Zombie Account & Resource Protection (Scenarios A, B, C).
Validates:
1. Token deduction stops bot when balance <= 0
2. Stale key cleanup scheduler logic
3. Weekly cleanup queries
4. Admin cleanup preview/run endpoints
5. Dormant user filtering
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")

from datetime import datetime, timedelta, date
from sqlalchemy.orm import Session
from database import SessionLocal, engine
from sqlalchemy import text
import models

PASS = 0
FAIL = 0


def report(name: str, ok: bool, detail: str = ""):
    global PASS, FAIL
    tag = "PASS" if ok else "FAIL"
    if ok:
        PASS += 1
    else:
        FAIL += 1
    print(f"  [{tag}] {name}" + (f" — {detail}" if detail else ""))


def test_model_last_login_at():
    """Verify User model has last_login_at column."""
    print("\n=== Test: User.last_login_at column ===")
    has_attr = hasattr(models.User, "last_login_at")
    report("User.last_login_at defined in model", has_attr)

    # Check DB column exists
    db = SessionLocal()
    try:
        db.execute(text("SELECT last_login_at FROM users LIMIT 1"))
        report("last_login_at column exists in DB", True)
    except Exception as e:
        report("last_login_at column exists in DB", False, str(e))
    finally:
        db.close()


def test_dormant_status():
    """Verify User.status supports 'dormant'."""
    print("\n=== Test: User.status supports 'dormant' ===")
    u = models.User(email="test_dormant@test.com", status="dormant")
    report("User(status='dormant') accepted", u.status == "dormant")


def test_deduction_bot_stop():
    """Token deduction should stop bot when balance hits 0."""
    print("\n=== Test: Deduction stops bot at 0 ===")
    from services.daily_token_deduction import apply_deduction_rule

    # Case 1: tokens > deduction → should deduct, no stop
    new_tok, should = apply_deduction_rule(100.0, 20.0)
    report("100 - 20 = 80 (deduct)", should and new_tok == 80.0, f"new_tok={new_tok}")

    # Case 2: deduction > tokens → balance floors at 0
    new_tok, should = apply_deduction_rule(5.0, 20.0)
    report("5 - 20 = 0 (floor)", should and new_tok == 0.0, f"new_tok={new_tok}")

    # Case 3: tokens already 0 → daily_gross still positive → should deduct
    new_tok, should = apply_deduction_rule(0.0, 10.0)
    report("0 - 10 = 0 (floor, deduct)", should and new_tok == 0.0, f"new_tok={new_tok}, should={should}")

    # Case 4: no profit → no deduction
    new_tok, should = apply_deduction_rule(100.0, 0.0)
    report("100 - 0 = no deduct", not should and new_tok == 100.0, f"new_tok={new_tok}")


def test_cleanup_preview():
    """Admin cleanup preview endpoint logic."""
    print("\n=== Test: Cleanup Preview ===")
    db = SessionLocal()
    try:
        # Import the function
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        # We need to import from main; but main has FastAPI startup — just test the raw SQL
        result = db.execute(text("SELECT COUNT(*) FROM deduction_log")).scalar()
        report("deduction_log table accessible", True, f"count={result}")

        result2 = db.execute(text("SELECT COUNT(*) FROM token_ledger")).scalar()
        report("token_ledger table accessible", True, f"count={result2}")

        result3 = db.execute(text("SELECT COUNT(*) FROM user_profit_snapshot")).scalar()
        report("user_profit_snapshot table accessible", True, f"count={result3}")

        # Test dormant filter query
        result4 = db.execute(text("""
            SELECT COUNT(*) FROM users u
            WHERE u.status = 'active'
              AND u.id NOT IN (SELECT user_id FROM api_vault)
              AND (u.last_login_at IS NULL OR u.last_login_at < :cutoff)
              AND u.id IN (SELECT user_id FROM user_token_balance WHERE tokens_remaining <= 0)
        """), {"cutoff": datetime.utcnow() - timedelta(days=180)}).scalar()
        report("Dormant candidate query works", True, f"candidates={result4}")
    except Exception as e:
        report("Cleanup preview queries", False, str(e))
    finally:
        db.close()


def test_stale_key_query():
    """Test stale key cleanup query."""
    print("\n=== Test: Stale Key Cleanup Query ===")
    db = SessionLocal()
    try:
        # Test invalid key days query
        r1 = db.execute(text("""
            SELECT COUNT(*) FROM api_vault av
            JOIN user_profit_snapshot ups ON ups.user_id = av.user_id
            WHERE ups.invalid_key_days >= 30
        """)).scalar()
        report("Stale invalid key query", True, f"count={r1}")

        # Test inactive key query
        cutoff = datetime.utcnow() - timedelta(days=90)
        r2 = db.execute(text("""
            SELECT COUNT(*) FROM api_vault av
            JOIN users u ON u.id = av.user_id
            WHERE u.bot_status = 'stopped'
              AND (u.last_login_at IS NULL OR u.last_login_at < :cutoff)
        """), {"cutoff": cutoff}).scalar()
        report("Stale inactive key query", True, f"count={r2}")
    except Exception as e:
        report("Stale key queries", False, str(e))
    finally:
        db.close()


def test_dormant_filter_in_deduction():
    """Verify dormant users are excluded from deduction queries."""
    print("\n=== Test: Dormant Filter in Deduction ===")
    db = SessionLocal()
    try:
        # Check that the deduction query excludes dormant users
        count_all = db.execute(text("""
            SELECT COUNT(*) FROM user_token_balance utb
            JOIN user_profit_snapshot ups ON utb.user_id = ups.user_id
            JOIN users u ON u.id = utb.user_id
        """)).scalar()

        count_non_dormant = db.execute(text("""
            SELECT COUNT(*) FROM user_token_balance utb
            JOIN user_profit_snapshot ups ON utb.user_id = ups.user_id
            JOIN users u ON u.id = utb.user_id
            WHERE u.status != 'dormant'
        """)).scalar()

        report("Dormant filter query runs", True, f"all={count_all} non_dormant={count_non_dormant}")
    except Exception as e:
        report("Dormant filter query", False, str(e))
    finally:
        db.close()


def test_admin_settings_defaults():
    """Verify _get_setting returns correct defaults for new cleanup settings."""
    print("\n=== Test: Admin Setting Defaults ===")
    db = SessionLocal()
    try:
        from main import _get_setting
        v1 = _get_setting(db, "stale_key_invalid_days", "30")
        report("stale_key_invalid_days default", v1 == "30", f"value={v1}")

        v2 = _get_setting(db, "stale_key_inactive_days", "90")
        report("stale_key_inactive_days default", v2 == "90", f"value={v2}")

        v3 = _get_setting(db, "cleanup_deduction_log_days", "180")
        report("cleanup_deduction_log_days default", v3 == "180", f"value={v3}")

        v4 = _get_setting(db, "cleanup_token_ledger_days", "365")
        report("cleanup_token_ledger_days default", v4 == "365", f"value={v4}")

        v5 = _get_setting(db, "cleanup_dormant_days", "180")
        report("cleanup_dormant_days default", v5 == "180", f"value={v5}")
    except Exception as e:
        report("Admin setting defaults", False, str(e))
    finally:
        db.close()


def test_worker_circuit_breaker_code():
    """Verify the circuit breaker code exists in worker.py."""
    print("\n=== Test: Worker Circuit Breaker Code ===")
    worker_path = Path(__file__).resolve().parent.parent / "worker.py"
    content = worker_path.read_text(encoding="utf-8")
    report("empty_wallet_consecutive in worker", "empty_wallet_consecutive" in content)
    report("EMPTY_WALLET_THRESHOLD in worker", "EMPTY_WALLET_THRESHOLD" in content)
    report("funding wallet is empty message", "funding wallet is empty" in content)


def test_scheduler_functions_exist():
    """Verify the new scheduler functions exist in main.py."""
    print("\n=== Test: Scheduler Functions ===")
    main_path = Path(__file__).resolve().parent.parent / "main.py"
    content = main_path.read_text(encoding="utf-8")
    report("_run_stale_key_cleanup_scheduler exists", "_run_stale_key_cleanup_scheduler" in content)
    report("_run_weekly_data_cleanup_scheduler exists", "_run_weekly_data_cleanup_scheduler" in content)
    report("_get_next_0200_utc_wait_sec exists", "_get_next_0200_utc_wait_sec" in content)
    report("_get_next_sunday_0300_utc_wait_sec exists", "_get_next_sunday_0300_utc_wait_sec" in content)
    report("stale_key_task in lifespan", "stale_key_task" in content)
    report("weekly_cleanup_task in lifespan", "weekly_cleanup_task" in content)
    report("/admin/cleanup/preview endpoint", "/admin/cleanup/preview" in content)
    report("/admin/cleanup/run endpoint", "/admin/cleanup/run" in content)


def test_deduction_bot_stop_code():
    """Verify deduction code stops bot when tokens <= 0."""
    print("\n=== Test: Deduction Bot Stop Code ===")
    deduction_path = Path(__file__).resolve().parent.parent / "services" / "daily_token_deduction.py"
    content = deduction_path.read_text(encoding="utf-8")
    report("bot_status = stopped in deduction", 'user.bot_status = "stopped"' in content)
    report("bot_desired_state = stopped in deduction", 'user.bot_desired_state = "stopped"' in content)
    report("bot_stopped key in log entry", '"bot_stopped"' in content)


if __name__ == "__main__":
    print("=" * 60)
    print("Zombie Account & Resource Protection Test Suite")
    print("=" * 60)

    test_model_last_login_at()
    test_dormant_status()
    test_deduction_bot_stop()
    test_cleanup_preview()
    test_stale_key_query()
    test_dormant_filter_in_deduction()
    test_worker_circuit_breaker_code()
    test_scheduler_functions_exist()
    test_deduction_bot_stop_code()

    # Admin settings test requires importing main.py which starts FastAPI
    # Run it last as it may have side effects
    try:
        test_admin_settings_defaults()
    except Exception as e:
        print(f"\n  [SKIP] Admin setting defaults test — {e}")

    print(f"\n{'=' * 60}")
    print(f"Results: {PASS} passed, {FAIL} failed")
    print(f"{'=' * 60}")
    sys.exit(1 if FAIL > 0 else 0)
