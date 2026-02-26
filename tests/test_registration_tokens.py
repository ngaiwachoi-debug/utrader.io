"""
Unit test: 150 tokens are awarded to user_token_balance on registration.

Run from project root:
  python -m pytest tests/test_registration_tokens.py -v
  or: python tests/test_registration_tokens.py
"""
import sys
from pathlib import Path

# Add project root so we can import main, database, models
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_award_registration_tokens_creates_record_with_150_tokens():
    """New user with no user_token_balance gets a row with tokens_remaining=150."""
    import database
    import models
    from main import _award_registration_tokens, REGISTRATION_TOKEN_AWARD

    db = database.SessionLocal()
    user_id = None
    try:
        # Create a user without going through registration (so no token award yet)
        email = f"test-registration-tokens-{id(db)}@gmail.com"
        user = models.User(
            email=email,
            plan_tier="trial",
            lending_limit=250_000.0,
            rebalance_interval=30,
        )
        user.referral_code = f"ref-{abs(hash(email)) % 10_000_000}"
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id

        # Award registration tokens (same as registration flow)
        _award_registration_tokens(user_id, db)

        # Assert: user_token_balance exists and has 150 tokens
        row = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).first()
        assert row is not None, "user_token_balance row should exist"
        assert row.tokens_remaining == float(REGISTRATION_TOKEN_AWARD), (
            f"tokens_remaining should be {REGISTRATION_TOKEN_AWARD}, got {row.tokens_remaining}"
        )
        # Registration stores bonus (150 - 100 trial) as purchased_tokens so API shows 150
        assert row.purchased_tokens == 50.0, f"purchased_tokens should be 50 (registration bonus), got {row.purchased_tokens}"
        assert row.last_gross_usd_used == 0.0
    finally:
        # Cleanup: delete token row and user
        if user_id is not None:
            db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).delete()
            db.query(models.User).filter(models.User.id == user_id).delete()
            db.commit()
        db.close()


def test_award_registration_tokens_adds_150_when_record_exists():
    """Existing user_token_balance: 150 is added to tokens_remaining (edge case)."""
    import database
    import models
    from main import _award_registration_tokens, REGISTRATION_TOKEN_AWARD

    db = database.SessionLocal()
    user_id = None
    try:
        email = f"test-registration-edge-{id(db)}@gmail.com"
        user = models.User(
            email=email,
            plan_tier="trial",
            lending_limit=250_000.0,
            rebalance_interval=30,
        )
        user.referral_code = f"ref-{abs(hash(email)) % 10_000_000}"
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id

        # Pre-create a token balance row (edge case)
        existing = models.UserTokenBalance(
            user_id=user_id,
            tokens_remaining=100.0,
            purchased_tokens=0.0,
            last_gross_usd_used=0.0,
        )
        db.add(existing)
        db.commit()

        # Award registration tokens (should add 150, not overwrite)
        _award_registration_tokens(user_id, db)

        row = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).first()
        assert row is not None
        assert row.tokens_remaining == 100.0 + REGISTRATION_TOKEN_AWARD, (
            f"tokens_remaining should be 250.0, got {row.tokens_remaining}"
        )
        assert row.purchased_tokens == 50.0, f"purchased_tokens should be 50 (bonus added), got {row.purchased_tokens}"
    finally:
        if user_id is not None:
            db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).delete()
            db.query(models.User).filter(models.User.id == user_id).delete()
            db.commit()
        db.close()


if __name__ == "__main__":
    test_award_registration_tokens_creates_record_with_150_tokens()
    test_award_registration_tokens_adds_150_when_record_exists()
    print("All tests passed.")
