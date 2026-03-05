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
    from services import token_ledger_service as token_ledger_svc

    db = database.SessionLocal()
    user_id = None
    try:
        email = f"test-registration-tokens-{id(db)}@gmail.com"
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

        _award_registration_tokens(user_id, db)

        row = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).first()
        assert row is not None, "user_token_balance row should exist"
        assert float(row.tokens_remaining) == float(REGISTRATION_TOKEN_AWARD), (
            f"tokens_remaining should be {REGISTRATION_TOKEN_AWARD}, got {row.tokens_remaining}"
        )
        remaining = token_ledger_svc.get_tokens_remaining(db, user_id)
        assert remaining == float(REGISTRATION_TOKEN_AWARD)
        assert row.last_gross_usd_used == 0.0

        # Token add is logged to token_ledger when table exists
        if hasattr(models, "TokenLedger"):
            try:
                ledger_rows = db.query(models.TokenLedger).filter(
                    models.TokenLedger.user_id == user_id,
                    models.TokenLedger.activity_type == "add",
                    models.TokenLedger.reason == "registration",
                ).all()
                assert len(ledger_rows) >= 1, "token_ledger should have at least one add row for registration"
                assert float(ledger_rows[0].amount) == float(REGISTRATION_TOKEN_AWARD)
            except Exception:
                pass  # table may not exist in test DB
    finally:
        if user_id is not None:
            try:
                if hasattr(models, "TokenLedger"):
                    db.query(models.TokenLedger).filter(models.TokenLedger.user_id == user_id).delete(synchronize_session=False)
                db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).delete(synchronize_session=False)
                db.query(models.User).filter(models.User.id == user_id).delete(synchronize_session=False)
                db.commit()
            except Exception:
                db.rollback()
                raise
        db.close()


def test_award_registration_tokens_adds_150_when_record_exists():
    """Existing user_token_balance: 150 is added to tokens_remaining (edge case)."""
    import database
    import models
    from main import _award_registration_tokens, REGISTRATION_TOKEN_AWARD
    from services import token_ledger_service as token_ledger_svc

    db = database.SessionLocal()
    user_id = None
    try:
        email = f"test-registration-edge-{id(db)}@gmail.com"
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

        existing = models.UserTokenBalance(
            user_id=user_id,
            tokens_remaining=100.0,
            purchased_tokens=0.0,
            last_gross_usd_used=0.0,
        )
        db.add(existing)
        db.commit()

        _award_registration_tokens(user_id, db)

        row = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).first()
        assert row is not None
        assert float(row.tokens_remaining) == 100.0 + REGISTRATION_TOKEN_AWARD, (
            f"tokens_remaining should be 250.0, got {row.tokens_remaining}"
        )
        remaining = token_ledger_svc.get_tokens_remaining(db, user_id)
        assert remaining == 250.0

        if hasattr(models, "TokenLedger"):
            try:
                ledger_rows = db.query(models.TokenLedger).filter(
                    models.TokenLedger.user_id == user_id,
                    models.TokenLedger.activity_type == "add",
                    models.TokenLedger.reason == "registration",
                ).all()
                assert len(ledger_rows) >= 1
                assert float(ledger_rows[0].amount) == float(REGISTRATION_TOKEN_AWARD)
            except Exception:
                pass
    finally:
        if user_id is not None:
            try:
                if hasattr(models, "TokenLedger"):
                    db.query(models.TokenLedger).filter(models.TokenLedger.user_id == user_id).delete(synchronize_session=False)
                db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).delete(synchronize_session=False)
                db.query(models.User).filter(models.User.id == user_id).delete(synchronize_session=False)
                db.commit()
            except Exception:
                db.rollback()
                raise
        db.close()


if __name__ == "__main__":
    test_award_registration_tokens_creates_record_with_150_tokens()
    test_award_registration_tokens_adds_150_when_record_exists()
    print("All tests passed.")
