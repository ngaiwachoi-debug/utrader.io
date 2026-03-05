"""
Tests for Bitfinex-derived auto calculations: token deduction, snapshot flow, formula consistency.

Pipeline: 10:00 UTC Bitfinex fetch -> user_profit_snapshot.daily_gross_profit_usd;
          10:30 UTC deduction uses snapshot only (no API). 1 USD gross = 1 token deducted.
          used_tokens (display) = gross_profit_usd * TOKENS_PER_USDT_GROSS (10).

Run from project root:
  python -m pytest tests/test_bitfinex_auto_calculation.py -v
  or: python tests/test_bitfinex_auto_calculation.py
"""
import sys
from pathlib import Path
from datetime import date, datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def test_apply_deduction_rule_cases():
    """Deduction rule: new = max(0, tokens_remaining - daily_gross); no deduct if profit <= 0."""
    from services.daily_token_deduction import apply_deduction_rule

    # Normal
    new, deduct = apply_deduction_rule(2000.0, 500.0)
    assert deduct is True and new == 1500.0
    # Clamp to zero
    new, deduct = apply_deduction_rule(100.0, 200.0)
    assert deduct is True and new == 0.0
    # No deduct: zero profit
    new, deduct = apply_deduction_rule(500.0, 0.0)
    assert deduct is False and new == 500.0
    # No deduct: negative profit
    new, deduct = apply_deduction_rule(500.0, -10.0)
    assert deduct is False and new == 500.0


def test_run_deduction_uses_snapshot_and_updates_balance():
    """Full run: snapshot.daily_gross_profit_usd (as set by Bitfinex fetch) -> deduct 1:1 USD from tokens."""
    import database
    import models
    from services.daily_token_deduction import run_daily_token_deduction

    db = database.SessionLocal()
    user_id = None
    try:
        email = f"bitfinex-auto-{id(db)}@test.local"
        user = models.User(email=email, plan_tier="trial", rebalance_interval=30)
        user.referral_code = f"ref-{abs(hash(email)) % 10_000_000}"
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id

        tokens_before = 3000.0
        daily_gross_from_bitfinex = 722.0  # as if 10:00 UTC fetch wrote this
        # Use purchased_tokens=0 so referral_rewards is not triggered (purchased_burned=0).
        db.add(models.UserTokenBalance(
            user_id=user_id,
            tokens_remaining=tokens_before,
            purchased_tokens=0.0,
            last_gross_usd_used=0.0,
        ))
        snap = models.UserProfitSnapshot(
            user_id=user_id,
            gross_profit_usd=722.0,  # cumulative
            daily_gross_profit_usd=daily_gross_from_bitfinex,
        )
        if hasattr(snap, "last_daily_snapshot_date"):
            snap.last_daily_snapshot_date = datetime.now(timezone.utc).date()
        db.add(snap)
        db.commit()

        log_entries, err = run_daily_token_deduction(db, user_ids=[user_id])
        assert err is None, err
        assert len(log_entries) == 1
        assert log_entries[0]["tokens_deducted"] == daily_gross_from_bitfinex
        assert log_entries[0]["tokens_remaining_before"] == tokens_before
        expected_after = tokens_before - daily_gross_from_bitfinex
        assert abs(log_entries[0]["tokens_remaining_after"] - expected_after) < 0.01

        row = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).first()
        assert row is not None
        assert abs(float(row.tokens_remaining) - expected_after) < 0.01
        assert abs(float(row.last_gross_usd_used) - daily_gross_from_bitfinex) < 0.01
    finally:
        if user_id is not None:
            if hasattr(models, "TokenLedger"):
                db.query(models.TokenLedger).filter(models.TokenLedger.user_id == user_id).delete(synchronize_session=False)
            if hasattr(models, "DeductionLog"):
                db.query(models.DeductionLog).filter(models.DeductionLog.user_id == user_id).delete(synchronize_session=False)
            db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).delete(synchronize_session=False)
            db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).delete(synchronize_session=False)
            db.query(models.User).filter(models.User.id == user_id).delete(synchronize_session=False)
            db.commit()
        db.close()


def test_used_tokens_formula_consistency():
    """used_tokens (display) = gross_profit_usd * TOKENS_PER_USDT_GROSS (10)."""
    from services.daily_token_deduction import TOKENS_PER_USDT_GROSS

    assert TOKENS_PER_USDT_GROSS == 10
    # As in deduction log and docs
    gross = 72.20
    used = int(gross * TOKENS_PER_USDT_GROSS)
    assert used == 722


def test_deduction_skipped_when_already_processed_today():
    """Same-day deduction is not run twice (last_deduction_processed_date)."""
    import database
    import models
    from services.daily_token_deduction import run_daily_token_deduction

    db = database.SessionLocal()
    user_id = None
    try:
        email = f"bitfinex-double-{id(db)}@test.local"
        user = models.User(email=email, plan_tier="trial", rebalance_interval=30)
        user.referral_code = f"ref-{abs(hash(email)) % 10_000_000}"
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id

        db.add(models.UserTokenBalance(
            user_id=user_id,
            tokens_remaining=1000.0,
            purchased_tokens=1000.0,
            last_gross_usd_used=0.0,
        ))
        now_utc = datetime.now(timezone.utc)
        date_utc = now_utc.date()
        snap = models.UserProfitSnapshot(
            user_id=user_id,
            gross_profit_usd=100.0,
            daily_gross_profit_usd=50.0,
        )
        if hasattr(models.UserProfitSnapshot, "last_deduction_processed_date"):
            snap.last_deduction_processed_date = date_utc
        db.add(snap)
        db.commit()

        log_entries, err = run_daily_token_deduction(db, user_ids=[user_id])
        assert err is None, (err or "no error message")
        # Should skip this user (already processed today)
        assert len(log_entries) == 0
        row = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).first()
        assert float(row.tokens_remaining) == 1000.0
    finally:
        if user_id is not None:
            db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).delete()
            db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).delete()
            db.query(models.User).filter(models.User.id == user_id).delete()
            db.commit()
        db.close()


def test_deduction_zero_daily_gross_skipped():
    """When daily_gross_profit_usd is 0 or None, no deduction and tokens unchanged."""
    import database
    import models
    from services.daily_token_deduction import run_daily_token_deduction

    db = database.SessionLocal()
    user_id = None
    try:
        email = f"bitfinex-zero-{id(db)}@test.local"
        user = models.User(email=email, plan_tier="trial", rebalance_interval=30)
        user.referral_code = f"ref-{abs(hash(email)) % 10_000_000}"
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id

        db.add(models.UserTokenBalance(
            user_id=user_id,
            tokens_remaining=1000.0,
            purchased_tokens=1000.0,
            last_gross_usd_used=0.0,
        ))
        db.add(models.UserProfitSnapshot(
            user_id=user_id,
            gross_profit_usd=0.0,
            daily_gross_profit_usd=0.0,
        ))
        db.commit()

        log_entries, err = run_daily_token_deduction(db, user_ids=[user_id])
        assert err is None
        assert len(log_entries) == 0
        row = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).first()
        assert float(row.tokens_remaining) == 1000.0
    finally:
        if user_id is not None:
            db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).delete()
            db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).delete()
            db.query(models.User).filter(models.User.id == user_id).delete()
            db.commit()
        db.close()


def test_token_balance_api_after_deduction():
    """GET /api/v1/users/me/token-balance returns correct values after deduction (derived total_tokens_deducted)."""
    import database
    import models
    from fastapi.testclient import TestClient
    from main import app, _get_current_user_for_token_balance
    from services.daily_token_deduction import run_daily_token_deduction

    db = database.SessionLocal()
    user_id = None
    try:
        email = f"bitfinex-api-{id(db)}@test.local"
        user = models.User(email=email, plan_tier="trial", rebalance_interval=30)
        user.referral_code = f"ref-{abs(hash(email)) % 10_000_000}"
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id

        # Use purchased_tokens=0 to avoid referral_rewards insert in test DB.
        purchased = 0.0
        tokens_before = 2000.0
        daily_gross = 500.0
        db.add(models.UserTokenBalance(
            user_id=user_id,
            tokens_remaining=tokens_before,
            purchased_tokens=purchased,
            last_gross_usd_used=0.0,
        ))
        snap = models.UserProfitSnapshot(
            user_id=user_id,
            gross_profit_usd=100.0,
            daily_gross_profit_usd=daily_gross,
        )
        if hasattr(snap, "last_daily_snapshot_date"):
            snap.last_daily_snapshot_date = datetime.now(timezone.utc).date()
        db.add(snap)
        db.commit()

        run_daily_token_deduction(db, user_ids=[user_id])

        def override_token_balance_user():
            return db.query(models.User).filter(models.User.id == user_id).first()

        app.dependency_overrides[_get_current_user_for_token_balance] = override_token_balance_user
        client = TestClient(app)
        try:
            r = client.get("/api/v1/users/me/token-balance")
            assert r.status_code == 200, r.text
            data = r.json()
            expected_remaining = round(tokens_before - daily_gross, 2)
            assert abs(data["tokens_remaining"] - expected_remaining) < 0.01
            assert abs(data["last_gross_usd_used"] - daily_gross) < 0.01
            # total_tokens_deducted derived from API (rounded); allow tolerance
            expected_deducted = max(0.0, purchased - (tokens_before - daily_gross))
            assert abs(data["total_tokens_deducted"] - expected_deducted) < 0.01
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
            db.query(models.User).filter(models.User.id == user_id).delete(synchronize_session=False)
            db.commit()
        db.close()


if __name__ == "__main__":
    test_apply_deduction_rule_cases()
    test_run_deduction_uses_snapshot_and_updates_balance()
    test_used_tokens_formula_consistency()
    test_deduction_skipped_when_already_processed_today()
    test_deduction_zero_daily_gross_skipped()
    test_token_balance_api_after_deduction()
    print("All Bitfinex auto-calculation tests passed.")
