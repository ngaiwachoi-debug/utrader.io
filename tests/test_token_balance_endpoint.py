"""
Unit tests for GET /api/v1/users/me/token-balance.

Run from project root:
  python -m pytest tests/test_token_balance_endpoint.py -v
  or: python tests/test_token_balance_endpoint.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_authenticated_user_returns_correct_balance():
    """Test 1: Authenticated user with token row → 200 and correct balance."""
    import database
    import models
    from fastapi.testclient import TestClient
    from main import app, _get_current_user_for_token_balance

    db = database.SessionLocal()
    user_id = None
    try:
        email = f"token-balance-test-{id(db)}@test.local"
        user = models.User(
            email=email,
            plan_tier="trial",
            rebalance_interval=30,
        )
        user.referral_code = f"ref-{abs(hash(email)) % 10_000_000}"
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id

        db.add(models.UserTokenBalance(
            user_id=user_id,
            tokens_remaining=1500.0,
            purchased_tokens=3500.0,
            last_gross_usd_used=500.0,
        ))
        db.commit()

        def override_token_balance_user():
            return db.query(models.User).filter(models.User.id == user_id).first()

        app.dependency_overrides[_get_current_user_for_token_balance] = override_token_balance_user
        client = TestClient(app)
        try:
            r = client.get("/api/v1/users/me/token-balance")
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["tokens_remaining"] == 1500.0
            assert data["total_tokens_added"] == 3500.0
            assert data["total_tokens_deducted"] == 2000.0
            assert data["last_gross_usd_used"] == 500.0
            assert data.get("updated_at") is None or isinstance(data["updated_at"], str)
        finally:
            app.dependency_overrides.pop(_get_current_user_for_token_balance, None)
    finally:
        if user_id is not None:
            db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).delete()
            db.query(models.User).filter(models.User.id == user_id).delete()
            db.commit()
        db.close()


def test_unauthenticated_returns_401():
    """Test 2: No Authorization header → 401 with detail 'Not authenticated'."""
    from fastapi.testclient import TestClient
    from main import app

    client = TestClient(app)
    r = client.get("/api/v1/users/me/token-balance")
    assert r.status_code == 401
    assert r.json().get("detail") == "Not authenticated"


def test_rate_limit_exceeded_returns_429():
    """Test 3: More than 10 requests in 1 minute → 429."""
    import database
    import models
    from fastapi.testclient import TestClient
    from main import app, _get_current_user_for_token_balance, TOKEN_BALANCE_RL_MAX

    db = database.SessionLocal()
    user_id = None
    try:
        email = f"token-balance-rl-{id(db)}@test.local"
        user = models.User(
            email=email,
            plan_tier="trial",
            rebalance_interval=30,
        )
        user.referral_code = f"ref-{abs(hash(email)) % 10_000_000}"
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
        db.add(models.UserTokenBalance(
            user_id=user_id,
            tokens_remaining=100.0,
            purchased_tokens=0.0,
        ))
        db.commit()

        def override_token_balance_user():
            return db.query(models.User).filter(models.User.id == user_id).first()

        app.dependency_overrides[_get_current_user_for_token_balance] = override_token_balance_user
        client = TestClient(app)
        try:
            for _ in range(TOKEN_BALANCE_RL_MAX + 1):
                r = client.get("/api/v1/users/me/token-balance")
            assert r.status_code == 429
            assert "Rate limit exceeded" in r.json().get("detail", "")
        finally:
            app.dependency_overrides.pop(_get_current_user_for_token_balance, None)
    finally:
        if user_id is not None:
            db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).delete()
            db.query(models.User).filter(models.User.id == user_id).delete()
            db.commit()
        db.close()


def test_no_user_token_balance_row_returns_404():
    """Test 4: User has no user_token_balance row → 404."""
    import database
    import models
    from fastapi.testclient import TestClient
    from main import app, _get_current_user_for_token_balance

    db = database.SessionLocal()
    user_id = None
    try:
        email = f"token-balance-norow-{id(db)}@test.local"
        user = models.User(
            email=email,
            plan_tier="trial",
            rebalance_interval=30,
        )
        user.referral_code = f"ref-{abs(hash(email)) % 10_000_000}"
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id

        def override_token_balance_user():
            return db.query(models.User).filter(models.User.id == user_id).first()

        app.dependency_overrides[_get_current_user_for_token_balance] = override_token_balance_user
        client = TestClient(app)
        try:
            r = client.get("/api/v1/users/me/token-balance")
            assert r.status_code == 404
        finally:
            app.dependency_overrides.pop(_get_current_user_for_token_balance, None)
    finally:
        if user_id is not None:
            db.query(models.User).filter(models.User.id == user_id).delete()
            db.commit()
        db.close()


def test_after_deduction_balance_updates():
    """Test 5: After run_daily_token_deduction, balance reflects deduction."""
    from datetime import datetime, timezone

    import database
    import models
    from fastapi.testclient import TestClient
    from main import app, _get_current_user_for_token_balance
    from services.daily_token_deduction import run_daily_token_deduction

    db = database.SessionLocal()
    user_id = None
    try:
        email = f"token-balance-deduction-{id(db)}@test.local"
        user = models.User(
            email=email,
            plan_tier="trial",
            rebalance_interval=30,
        )
        user.referral_code = f"ref-{abs(hash(email)) % 10_000_000}"
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id

        db.add(models.UserTokenBalance(
            user_id=user_id,
            tokens_remaining=2000.0,
            purchased_tokens=2000.0,
            last_gross_usd_used=0.0,
        ))
        snap = models.UserProfitSnapshot(
            user_id=user_id,
            gross_profit_usd=100.0,
            net_profit_usd=85.0,
            bitfinex_fee_usd=15.0,
            daily_gross_profit_usd=500.0,
        )
        if hasattr(snap, "last_daily_snapshot_date"):
            snap.last_daily_snapshot_date = datetime.now(timezone.utc).date()
        db.add(snap)
        db.commit()

        run_daily_token_deduction(db)

        def override_token_balance_user():
            return db.query(models.User).filter(models.User.id == user_id).first()

        app.dependency_overrides[_get_current_user_for_token_balance] = override_token_balance_user
        client = TestClient(app)
        try:
            r = client.get("/api/v1/users/me/token-balance")
            assert r.status_code == 200
            data = r.json()
            assert data["tokens_remaining"] == 1500.0  # 2000 - 500
            assert data["total_tokens_added"] == 2000.0
            assert data["total_tokens_deducted"] == 500.0
            assert data["last_gross_usd_used"] == 500.0
        finally:
            app.dependency_overrides.pop(_get_current_user_for_token_balance, None)
    finally:
        if user_id is not None:
            if hasattr(models, "TokenLedger"):
                db.query(models.TokenLedger).filter(models.TokenLedger.user_id == user_id).delete(synchronize_session=False)
            if hasattr(models, "DeductionLog"):
                db.query(models.DeductionLog).filter(models.DeductionLog.user_id == user_id).delete(synchronize_session=False)
            db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).delete(synchronize_session=False)
            db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).delete()
            db.query(models.User).filter(models.User.id == user_id).delete()
            db.commit()
        db.close()


if __name__ == "__main__":
    test_authenticated_user_returns_correct_balance()
    test_unauthenticated_returns_401()
    test_rate_limit_exceeded_returns_429()
    test_no_user_token_balance_row_returns_404()
    test_after_deduction_balance_updates()
    print("All tests passed.")
