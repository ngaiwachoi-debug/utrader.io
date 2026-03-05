"""
Unit tests: POST /api/v1/tokens/deposit validation and token calculation.
Token rule: tokens_to_award = int(usd_amount × 100) (1 USD = 100 tokens), minimum $1.

Run from project root:
  python -m pytest tests/test_token_deposits.py -v
  or: python tests/test_token_deposits.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _make_client_with_user(db_session=None, user_id=None):
    """Create a test client with get_current_user overridden to return a real DB user.
    If db_session and user_id are provided, the override returns that user; otherwise
    creates a temporary user and returns it (caller must cleanup).
    """
    from fastapi.testclient import TestClient
    import database
    import main
    import models

    db = db_session or database.SessionLocal()
    email = f"test-deposit-{id(db)}@test.com"
    user = models.User(email=email, plan_tier="trial", rebalance_interval=30)
    user.referral_code = f"ref-{abs(hash(email)) % 10_000_000}"
    db.add(user)
    db.commit()
    db.refresh(user)
    uid = user.id

    def override_current_user():
        return db.query(models.User).filter(models.User.id == uid).first()

    main.app.dependency_overrides[main.get_current_user] = override_current_user
    client = TestClient(main.app)
    return client, db, uid


def _cleanup_deposit_user(db, user_id):
    """Cleanup in order: TokenLedger, UserTokenBalance, User."""
    import models
    if user_id is None:
        return
    if hasattr(models, "TokenLedger"):
        db.query(models.TokenLedger).filter(models.TokenLedger.user_id == user_id).delete(synchronize_session=False)
    db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).delete(synchronize_session=False)
    db.query(models.User).filter(models.User.id == user_id).delete(synchronize_session=False)
    db.commit()


def _make_client():
    """Client with fake user (no DB write); for rejection tests that don't need a real user."""
    from fastapi.testclient import TestClient
    import main
    import models

    def fake_current_user():
        return models.User(id=999, email="test-deposit@test.com", plan_tier="trial")

    main.app.dependency_overrides[main.get_current_user] = fake_current_user
    return TestClient(main.app)


def test_calculate_tokens_50_usd():
    """$50 → 5000 tokens (1 USD = 100 tokens)."""
    import database
    import main

    db = database.SessionLocal()
    client, db, uid = _make_client_with_user(db_session=db)
    try:
        r = client.post("/api/v1/tokens/deposit", json={"usd_amount": 50})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("status") == "success"
        assert data.get("usd_amount") == 50.0
        assert data.get("tokens_to_award") == 5000
    finally:
        main.app.dependency_overrides.pop(main.get_current_user, None)
        _cleanup_deposit_user(db, uid)
        db.close()


def test_calculate_tokens_10_99_usd():
    """$10.99 → 1099 tokens (1 USD = 100 tokens, int truncation)."""
    import database
    import main

    db = database.SessionLocal()
    client, db, uid = _make_client_with_user(db_session=db)
    try:
        r = client.post("/api/v1/tokens/deposit", json={"usd_amount": 10.99})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("status") == "success"
        assert data.get("usd_amount") == 10.99
        assert data.get("tokens_to_award") == 1099
    finally:
        main.app.dependency_overrides.pop(main.get_current_user, None)
        _cleanup_deposit_user(db, uid)
        db.close()


def test_calculate_tokens_120_50_usd():
    """$120.50 → 12050 tokens (1 USD = 100 tokens)."""
    import database
    import main

    db = database.SessionLocal()
    client, db, uid = _make_client_with_user(db_session=db)
    try:
        r = client.post("/api/v1/tokens/deposit", json={"usd_amount": 120.50})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("status") == "success"
        assert data.get("usd_amount") == 120.5
        assert data.get("tokens_to_award") == 12050
    finally:
        main.app.dependency_overrides.pop(main.get_current_user, None)
        _cleanup_deposit_user(db, uid)
        db.close()


def test_reject_0_99_usd():
    """$0.99 → 400 error (minimum $1)."""
    client = _make_client()
    try:
        r = client.post("/api/v1/tokens/deposit", json={"usd_amount": 0.99})
        assert r.status_code == 400, r.text
        data = r.json()
        assert data.get("status") == "error"
        assert "minimum" in data.get("message", "").lower() or "1" in data.get("message", "")
    finally:
        client.app.dependency_overrides.clear()


def test_reject_negative_usd():
    """Negative amount → 400 error."""
    client = _make_client()
    try:
        r = client.post("/api/v1/tokens/deposit", json={"usd_amount": -10})
        assert r.status_code == 400, r.text
        data = r.json()
        assert data.get("status") == "error"
    finally:
        client.app.dependency_overrides.clear()


def test_reject_non_numeric_usd():
    """Non-numeric usd_amount → 400 or 422 error."""
    client = _make_client()
    try:
        r = client.post("/api/v1/tokens/deposit", json={"usd_amount": "abc"})
        # Pydantic returns 422 for wrong type; our endpoint returns 400 for float parsing
        assert r.status_code in (400, 422), r.text
        data = r.json()
        if r.status_code == 400:
            assert data.get("status") == "error"
        else:
            assert "detail" in data
    finally:
        client.app.dependency_overrides.clear()


if __name__ == "__main__":
    test_calculate_tokens_50_usd()
    test_calculate_tokens_10_99_usd()
    test_calculate_tokens_120_50_usd()
    test_reject_0_99_usd()
    test_reject_negative_usd()
    test_reject_non_numeric_usd()
    print("All tests passed.")
