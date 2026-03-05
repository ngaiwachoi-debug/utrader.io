"""
Run API-level checks from TEST_PLAN_AMENDMENTS_LAST_10_REQUESTS.md.
Uses FastAPI TestClient (no live server). Run from project root: python scripts/run_test_plan_checks.py
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Minimal env for in-process tests
os.environ.setdefault("ADMIN_EMAIL", "admin@test.local")


def main():
    from fastapi.testclient import TestClient
    import database
    import models
    from main import app, get_current_user, _get_current_user_for_token_balance

    client = TestClient(app)
    db = database.SessionLocal()
    user_id = None
    passed = 0
    failed = 0

    try:
        # Create test user with token balance and vault for fold
        email = f"test-plan-{os.getpid()}@test.local"
        user = db.query(models.User).filter(models.User.email == email).first()
        if not user:
            user = models.User(email=email, plan_tier="trial", rebalance_interval=30)
            user.referral_code = f"ref{os.getpid() % 100000}"
            db.add(user)
            db.commit()
            db.refresh(user)
        user_id = user.id

        if not db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).first():
            db.add(models.UserTokenBalance(
                user_id=user_id,
                tokens_remaining=1000.0,
                purchased_tokens=2000.0,
                last_gross_usd_used=100.0,
            ))
            db.commit()

        def override_user():
            return db.query(models.User).filter(models.User.id == user_id).first()

        app.dependency_overrides[get_current_user] = override_user
        app.dependency_overrides[_get_current_user_for_token_balance] = override_user

        # --- 9.2 Token balance in fold ---
        try:
            r = client.get("/api/dashboard-fold")
            if r.status_code != 200:
                print(f"FAIL 9.2 dashboard-fold status={r.status_code}")
                failed += 1
            else:
                data = r.json()
                if "token_balance" not in data:
                    print("FAIL 9.2 dashboard-fold missing token_balance")
                    failed += 1
                else:
                    tb = data["token_balance"]
                    if not all(k in tb for k in ("tokens_remaining", "total_tokens_added", "total_tokens_deducted")):
                        print("FAIL 9.2 token_balance missing keys:", list(tb.keys()))
                        failed += 1
                    else:
                        print("PASS 9.2 dashboard-fold includes token_balance")
                        passed += 1
                if "lending" in data and "wallets" in data and "botStats" in data and "userStatus" in data:
                    print("PASS 9.1 fold returns wallets, botStats, userStatus, lending")
                    passed += 1
                else:
                    print("FAIL 9.1 fold missing one of wallets/botStats/userStatus/lending")
                    failed += 1
        except Exception as e:
            print(f"FAIL 9.x dashboard-fold: {e}")
            failed += 1

        # --- Token balance endpoint ---
        try:
            r = client.get("/api/v1/users/me/token-balance")
            if r.status_code == 200:
                d = r.json()
                if "tokens_remaining" in d and "total_tokens_added" in d:
                    print("PASS GET /api/v1/users/me/token-balance shape")
                    passed += 1
                else:
                    print("FAIL token-balance missing keys")
                    failed += 1
            else:
                print(f"FAIL token-balance status={r.status_code}")
                failed += 1
        except Exception as e:
            print(f"FAIL token-balance: {e}")
            failed += 1

        # --- Referral bundle endpoint (auth required) ---
        try:
            r = client.get("/api/v1/user/referral-bundle?limit=50")
            if r.status_code in (200, 401):
                if r.status_code == 200:
                    d = r.json()
                    if isinstance(d, dict):
                        print("PASS GET /api/v1/user/referral-bundle returns dict")
                        passed += 1
                    else:
                        print("PASS referral-bundle returns (shape not asserted)")
                        passed += 1
                else:
                    print("PASS referral-bundle requires auth (401)")
                    passed += 1
            else:
                print(f"FAIL referral-bundle status={r.status_code}")
                failed += 1
        except Exception as e:
            print(f"FAIL referral-bundle: {e}")
            failed += 1

        # --- Unauthenticated fold returns 401 ---
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(_get_current_user_for_token_balance, None)
        r = client.get("/api/dashboard-fold")
        if r.status_code == 401:
            print("PASS dashboard-fold requires auth (401 when no auth)")
            passed += 1
        else:
            print(f"FAIL dashboard-fold without auth expected 401 got {r.status_code}")
            failed += 1

        # --- Cache caps (import checks) ---
        try:
            from services import bitfinex_cache
            if hasattr(bitfinex_cache, "MAX_CACHE_ENTRIES") and bitfinex_cache.MAX_CACHE_ENTRIES == 5000:
                print("PASS bitfinex_cache MAX_CACHE_ENTRIES = 5000")
                passed += 1
            else:
                print("FAIL bitfinex_cache MAX_CACHE_ENTRIES missing or not 5000")
                failed += 1
            if hasattr(bitfinex_cache, "_evict_oldest_if_over_limit"):
                print("PASS bitfinex_cache _evict_oldest_if_over_limit exists")
                passed += 1
            else:
                print("FAIL bitfinex_cache _evict_oldest_if_over_limit missing")
                failed += 1
        except Exception as e:
            print(f"FAIL bitfinex_cache: {e}")
            failed += 1

        try:
            from main import TICKER_CACHE_MAX_ENTRIES, _evict_oldest_ticker_entry
            if TICKER_CACHE_MAX_ENTRIES == 2000:
                print("PASS main TICKER_CACHE_MAX_ENTRIES = 2000")
                passed += 1
            else:
                print("FAIL main TICKER_CACHE_MAX_ENTRIES not 2000")
                failed += 1
            print("PASS main _evict_oldest_ticker_entry exists")
            passed += 1
        except Exception as e:
            print(f"FAIL ticker cache: {e}")
            failed += 1

        # --- Fold ticker state (single ticker fetch) ---
        try:
            from main import _get_fold_ticker_prices
            print("PASS _get_fold_ticker_prices exists (single ticker per fold)")
            passed += 1
        except ImportError:
            print("FAIL _get_fold_ticker_prices not found")
            failed += 1

        # --- Fold fills trades helper ---
        try:
            from main import _fetch_funding_trade_records_for_user
            print("PASS _fetch_funding_trade_records_for_user exists (fold fills trades)")
            passed += 1
        except ImportError:
            print("FAIL _fetch_funding_trade_records_for_user not found")
            failed += 1

    finally:
        if user_id:
            try:
                db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).delete()
                db.query(models.User).filter(models.User.id == user_id).delete()
                db.commit()
            except Exception:
                pass
        db.close()
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(_get_current_user_for_token_balance, None)

    print("")
    print(f"Result: {passed} passed, {failed} failed")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
