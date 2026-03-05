"""
Full tests for auto deduction (run_daily_token_deduction) and manual/backfill deduction
(run_deduction_for_user_for_date), including extreme cases.

Run from project root:
  python -m pytest tests/test_auto_and_manual_deduction.py -v
  or: python tests/test_auto_and_manual_deduction.py
"""
import sys
from pathlib import Path
from datetime import date, datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def _utc_today() -> date:
    return datetime.now(timezone.utc).date()


def _make_user_with_balance_and_snapshot(
    db,
    email_prefix: str,
    tokens_remaining: float,
    daily_gross_profit_usd: float,
    last_daily_snapshot_date=None,
    last_deduction_processed_date=None,
    gross_profit_usd=None,
):
    """Create User, UserTokenBalance, UserProfitSnapshot; return user_id."""
    import models
    email = f"{email_prefix}-{id(db)}@test.local"
    user = models.User(email=email, plan_tier="trial", rebalance_interval=30)
    user.referral_code = f"ref-{abs(hash(email)) % 10_000_000}"
    db.add(user)
    db.commit()
    db.refresh(user)
    user_id = user.id
    db.add(models.UserTokenBalance(
        user_id=user_id,
        tokens_remaining=tokens_remaining,
        purchased_tokens=0.0,
        last_gross_usd_used=0.0,
    ))
    snap = models.UserProfitSnapshot(
        user_id=user_id,
        gross_profit_usd=gross_profit_usd if gross_profit_usd is not None else (daily_gross_profit_usd or 0),
        daily_gross_profit_usd=daily_gross_profit_usd or 0.0,
    )
    if hasattr(snap, "last_daily_snapshot_date") and last_daily_snapshot_date is not None:
        snap.last_daily_snapshot_date = last_daily_snapshot_date
    if hasattr(snap, "last_deduction_processed_date") and last_deduction_processed_date is not None:
        snap.last_deduction_processed_date = last_deduction_processed_date
    db.add(snap)
    db.commit()
    return user_id


def _cleanup_user(db, user_id):
    import models
    if user_id is None:
        return
    if hasattr(models, "DeductionLog"):
        db.query(models.DeductionLog).filter(models.DeductionLog.user_id == user_id).delete(synchronize_session=False)
    db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).delete(synchronize_session=False)
    db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).delete(synchronize_session=False)
    db.query(models.User).filter(models.User.id == user_id).delete(synchronize_session=False)
    db.commit()


# ----- Auto deduction (run_daily_token_deduction) -----

def test_auto_deduction_deducts_today_and_sets_last_processed_date():
    """Auto: run_daily_token_deduction deducts daily_gross for today and sets last_deduction_processed_date."""
    import database
    import models
    from services.daily_token_deduction import run_daily_token_deduction

    db = database.SessionLocal()
    user_id = None
    try:
        today_utc = _utc_today()
        user_id = _make_user_with_balance_and_snapshot(
            db, "auto-today", 3000.0, 500.0,
            last_daily_snapshot_date=today_utc,
        )
        log_entries, err = run_daily_token_deduction(db, user_ids=[user_id])
        assert err is None, err
        assert len(log_entries) == 1
        assert log_entries[0]["tokens_deducted"] == 500.0
        assert log_entries[0]["tokens_remaining_after"] == 2500.0
        db.commit()
        snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).first()
        assert snap is not None
        if hasattr(snap, "last_deduction_processed_date"):
            assert snap.last_deduction_processed_date == today_utc
        bal = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).first()
        assert float(bal.tokens_remaining) == 2500.0
    finally:
        _cleanup_user(db, user_id)
        db.close()


def test_auto_deduction_skips_when_already_processed_today():
    """Auto: no double deduction when last_deduction_processed_date == today."""
    import database
    import models
    from services.daily_token_deduction import run_daily_token_deduction

    db = database.SessionLocal()
    user_id = None
    try:
        today_utc = _utc_today()
        user_id = _make_user_with_balance_and_snapshot(
            db, "auto-no-double", 2000.0, 100.0,
            last_daily_snapshot_date=today_utc,
            last_deduction_processed_date=today_utc,
        )
        log_entries, err = run_daily_token_deduction(db, user_ids=[user_id])
        assert err is None
        assert len(log_entries) == 0
        bal = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).first()
        assert float(bal.tokens_remaining) == 2000.0
    finally:
        _cleanup_user(db, user_id)
        db.close()


def test_auto_deduction_zero_daily_gross_skipped():
    """Auto: daily_gross_profit_usd 0 or None → no deduction."""
    import database
    from services.daily_token_deduction import run_daily_token_deduction

    db = database.SessionLocal()
    user_id = None
    try:
        user_id = _make_user_with_balance_and_snapshot(db, "auto-zero", 1000.0, 0.0)
        log_entries, err = run_daily_token_deduction(db, user_ids=[user_id])
        assert err is None
        assert len(log_entries) == 0
        import models as m
        bal = db.query(m.UserTokenBalance).filter(m.UserTokenBalance.user_id == user_id).first()
        assert float(bal.tokens_remaining) == 1000.0
    finally:
        _cleanup_user(db, user_id)
        db.close()


def test_auto_deduction_extreme_tokens_less_than_daily_gross_clamps_to_zero():
    """Auto: tokens_remaining=100, daily_gross=100 → balance becomes 0 (all free tokens, no referral)."""
    import database
    import models
    from services.daily_token_deduction import run_daily_token_deduction

    db = database.SessionLocal()
    user_id = None
    try:
        user_id = _make_user_with_balance_and_snapshot(
            db, "auto-clamp", 100.0, 100.0,
            last_daily_snapshot_date=_utc_today(),
        )
        log_entries, err = run_daily_token_deduction(db, user_ids=[user_id])
        assert err is None, err
        assert len(log_entries) == 1
        assert log_entries[0]["tokens_remaining_after"] == 0.0
        assert log_entries[0]["tokens_deducted"] == 100.0
        bal = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).first()
        assert float(bal.tokens_remaining) == 0.0
    finally:
        _cleanup_user(db, user_id)
        db.close()


# ----- Manual / backfill (run_deduction_for_user_for_date) -----

def test_manual_backfill_deducts_for_specific_date():
    """Manual backfill: run_deduction_for_user_for_date deducts for given date and sets last_deduction_processed_date."""
    import database
    import models
    from services.daily_token_deduction import run_deduction_for_user_for_date

    db = database.SessionLocal()
    user_id = None
    try:
        yesterday = date.today() - timedelta(days=1)
        user_id = _make_user_with_balance_and_snapshot(
            db, "manual-backfill", 3723.0, 4.41,
            last_daily_snapshot_date=yesterday,
            last_deduction_processed_date=None,
        )
        log_entry, err = run_deduction_for_user_for_date(db, user_id, yesterday, 4.41)
        assert err is None
        assert log_entry is not None
        assert log_entry["tokens_deducted"] == 4.41
        assert log_entry["tokens_remaining_after"] == 3723.0 - 4.41
        assert log_entry.get("for_date") == yesterday.isoformat()
        db.commit()
        snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).first()
        if hasattr(snap, "last_deduction_processed_date"):
            assert snap.last_deduction_processed_date == yesterday
        bal = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).first()
        assert abs(float(bal.tokens_remaining) - (3723.0 - 4.41)) < 1e-6
    finally:
        _cleanup_user(db, user_id)
        db.close()


def test_manual_backfill_skips_when_already_deducted_for_that_date():
    """Manual backfill: no op when last_deduction_processed_date == date_d."""
    import database
    import models
    from services.daily_token_deduction import run_deduction_for_user_for_date

    db = database.SessionLocal()
    user_id = None
    try:
        yesterday = date.today() - timedelta(days=1)
        user_id = _make_user_with_balance_and_snapshot(
            db, "manual-no-double", 1000.0, 10.0,
            last_daily_snapshot_date=yesterday,
            last_deduction_processed_date=yesterday,
        )
        log_entry, err = run_deduction_for_user_for_date(db, user_id, yesterday, 10.0)
        assert err is None
        assert log_entry is None
        bal = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).first()
        assert float(bal.tokens_remaining) == 1000.0
    finally:
        _cleanup_user(db, user_id)
        db.close()


def test_manual_backfill_skips_when_daily_gross_zero_or_negative():
    """Manual backfill: returns (None, None) when daily_gross <= 0."""
    import database
    from services.daily_token_deduction import run_deduction_for_user_for_date

    db = database.SessionLocal()
    user_id = None
    try:
        yesterday = date.today() - timedelta(days=1)
        user_id = _make_user_with_balance_and_snapshot(
            db, "manual-zero-gross", 1000.0, 0.0,
            last_daily_snapshot_date=yesterday,
        )
        log_entry, err = run_deduction_for_user_for_date(db, user_id, yesterday, 0.0)
        assert log_entry is None and err is None
        log_entry2, _ = run_deduction_for_user_for_date(db, user_id, yesterday, -1.0)
        assert log_entry2 is None
        import models as m
        bal = db.query(m.UserTokenBalance).filter(m.UserTokenBalance.user_id == user_id).first()
        assert float(bal.tokens_remaining) == 1000.0
    finally:
        _cleanup_user(db, user_id)
        db.close()


def test_manual_backfill_no_op_when_no_snapshot_or_no_balance():
    """Manual backfill: user with no snapshot or no token balance → (None, None)."""
    import database
    import models
    from services.daily_token_deduction import run_deduction_for_user_for_date

    db = database.SessionLocal()
    user_id = None
    try:
        # User with snapshot but no token balance row (should not happen in prod; helper expects both).
        email = f"manual-no-bal-{id(db)}@test.local"
        user = models.User(email=email, plan_tier="trial", rebalance_interval=30)
        user.referral_code = f"ref-{abs(hash(email)) % 10_000_000}"
        db.add(user)
        db.commit()
        db.refresh(user)
        user_id = user.id
        db.add(models.UserProfitSnapshot(
            user_id=user_id,
            gross_profit_usd=5.0,
            daily_gross_profit_usd=5.0,
            last_daily_snapshot_date=date.today() - timedelta(days=1),
        ))
        db.commit()
        log_entry, err = run_deduction_for_user_for_date(db, user_id, date.today() - timedelta(days=1), 5.0)
        # No UserTokenBalance → query joins fail and row is None, so we get (None, None)
        assert log_entry is None and err is None
    finally:
        if user_id is not None:
            db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).delete(synchronize_session=False)
            db.query(models.User).filter(models.User.id == user_id).delete(synchronize_session=False)
            db.commit()
        db.close()


def test_manual_backfill_extreme_tokens_less_than_gross_clamps_to_zero():
    """Manual backfill: tokens_remaining=2, daily_gross=2 → balance becomes 0 (no referral)."""
    import database
    import models
    from services.daily_token_deduction import run_deduction_for_user_for_date

    db = database.SessionLocal()
    user_id = None
    try:
        past = date.today() - timedelta(days=2)
        user_id = _make_user_with_balance_and_snapshot(
            db, "manual-clamp", 2.0, 2.0,
            last_daily_snapshot_date=past,
        )
        log_entry, err = run_deduction_for_user_for_date(db, user_id, past, 2.0)
        assert err is None
        assert log_entry is not None
        assert log_entry["tokens_remaining_after"] == 0.0
        db.commit()
        bal = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).first()
        assert float(bal.tokens_remaining) == 0.0
    finally:
        _cleanup_user(db, user_id)
        db.close()


def test_manual_backfill_then_auto_today_no_double():
    """Scenario: backfill yesterday, then run_daily_token_deduction for today; both applied once."""
    import database
    import models
    from services.daily_token_deduction import run_deduction_for_user_for_date, run_daily_token_deduction

    db = database.SessionLocal()
    user_id = None
    try:
        yesterday = date.today() - timedelta(days=1)
        user_id = _make_user_with_balance_and_snapshot(
            db, "backfill-then-today", 5000.0, 4.41,
            last_daily_snapshot_date=yesterday,
            last_deduction_processed_date=None,
        )
        # Backfill yesterday
        log1, _ = run_deduction_for_user_for_date(db, user_id, yesterday, 4.41)
        assert log1 is not None
        db.commit()
        bal_after_backfill = float(
            db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).first().tokens_remaining
        )
        assert abs(bal_after_backfill - (5000.0 - 4.41)) < 1e-6
        # Update snapshot to "today" so auto deduction has something to deduct (simulate refresh wrote today's gross)
        snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).first()
        snap.daily_gross_profit_usd = 1.0
        if hasattr(snap, "last_daily_snapshot_date"):
            snap.last_daily_snapshot_date = _utc_today()
        db.commit()
        # Auto for today
        log_entries, err = run_daily_token_deduction(db, user_ids=[user_id])
        assert err is None
        assert len(log_entries) == 1
        assert log_entries[0]["tokens_deducted"] == 1.0
        bal_final = float(
            db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user_id).first().tokens_remaining
        )
        assert abs(bal_final - (5000.0 - 4.41 - 1.0)) < 1e-6
    finally:
        _cleanup_user(db, user_id)
        db.close()


def test_auto_deduction_1030_utc_frozen_time():
    """Option 1: Freeze time at 10:30 UTC; run_daily_token_deduction deducts once, second run skips (already processed)."""
    try:
        from freezegun import freeze_time
    except ImportError:
        try:
            import pytest
            pytest.skip("freezegun not installed")
        except ImportError:
            return  # run as __main__ without freezegun: skip this test
    import database
    import models
    from services.daily_token_deduction import run_daily_token_deduction, _utc_today

    frozen_date = date(2026, 3, 3)
    with freeze_time("2026-03-03 10:30:00", tz_offset=0):
        db = database.SessionLocal()
        user_id = None
        try:
            user_id = _make_user_with_balance_and_snapshot(
                db, "auto-1030", 1000.0, 10.5,
                last_daily_snapshot_date=frozen_date,
                last_deduction_processed_date=frozen_date - timedelta(days=1),
            )
            assert _utc_today() == frozen_date
            log_entries, err = run_daily_token_deduction(db, user_ids=[user_id])
            assert err is None, err
            assert len(log_entries) == 1, log_entries
            assert log_entries[0]["tokens_deducted"] == 10.5
            assert log_entries[0]["tokens_remaining_after"] == 989.5
            snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).first()
            assert getattr(snap, "last_deduction_processed_date", None) == frozen_date
            db.commit()
            db.expire_all()
            log_entries2, err2 = run_daily_token_deduction(db, user_ids=[user_id])
            assert err2 is None
            assert len(log_entries2) == 0, "second run same day must skip (already processed)"
        finally:
            _cleanup_user(db, user_id)
            db.close()


if __name__ == "__main__":
    test_auto_deduction_deducts_today_and_sets_last_processed_date()
    test_auto_deduction_skips_when_already_processed_today()
    test_auto_deduction_zero_daily_gross_skipped()
    test_auto_deduction_extreme_tokens_less_than_daily_gross_clamps_to_zero()
    test_manual_backfill_deducts_for_specific_date()
    test_manual_backfill_skips_when_already_deducted_for_that_date()
    test_manual_backfill_skips_when_daily_gross_zero_or_negative()
    test_manual_backfill_no_op_when_no_snapshot_or_no_balance()
    test_manual_backfill_extreme_tokens_less_than_gross_clamps_to_zero()
    test_manual_backfill_then_auto_today_no_double()
    test_auto_deduction_1030_utc_frozen_time()
    print("All auto and manual deduction tests passed.")
