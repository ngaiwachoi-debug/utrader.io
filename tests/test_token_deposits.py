"""
Unit tests: POST /api/v1/tokens/deposit validation and token calculation.
Token rule: tokens_to_award = round(usd_amount × 10), minimum $1.

Run from project root:
  python -m pytest tests/test_token_deposits.py -v
  or: python tests/test_token_deposits.py
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _make_client():
    from fastapi.testclient import TestClient
    import main
    import models

    app = main.app
    # Override auth so we don't need a real user in DB
    def fake_current_user():
        return models.User(id=999, email="test-deposit@test.com", plan_tier="trial")

    app.dependency_overrides[main.get_current_user] = fake_current_user
    client = TestClient(app)
    return client


def test_calculate_tokens_50_usd():
    """$50 → 500 tokens."""
    client = _make_client()
    try:
        r = client.post("/api/v1/tokens/deposit", json={"usd_amount": 50})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("status") == "success"
        assert data.get("usd_amount") == 50.0
        assert data.get("tokens_to_award") == 500
    finally:
        client.app.dependency_overrides.clear()


def test_calculate_tokens_10_99_usd():
    """$10.99 → 109 tokens (round to nearest integer)."""
    client = _make_client()
    try:
        r = client.post("/api/v1/tokens/deposit", json={"usd_amount": 10.99})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("status") == "success"
        assert data.get("usd_amount") == 10.99
        assert data.get("tokens_to_award") == 109
    finally:
        client.app.dependency_overrides.clear()


def test_calculate_tokens_120_50_usd():
    """$120.50 → 1205 tokens."""
    client = _make_client()
    try:
        r = client.post("/api/v1/tokens/deposit", json={"usd_amount": 120.50})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data.get("status") == "success"
        assert data.get("usd_amount") == 120.5
        assert data.get("tokens_to_award") == 1205
    finally:
        client.app.dependency_overrides.clear()


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
