"""
Token service: user_token_balance is source of truth; token_ledger logs every add for history.
"""
from sqlalchemy.orm import Session
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

try:
    import models
    _has_token_ledger = hasattr(models, "TokenLedger")
except Exception:
    _has_token_ledger = False


def _token_ledger_table_exists(db: Session) -> bool:
    """Return True if token_ledger table exists. Uses information_schema to avoid failing the transaction."""
    global _has_token_ledger
    if not _has_token_ledger:
        return False
    try:
        r = db.execute(
            text("SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'token_ledger'")
        ).fetchone()
        if not r:
            _has_token_ledger = False
            return False
        return True
    except Exception:
        _has_token_ledger = False
        return False

PURCHASED_REASONS = frozenset({
    "deposit_usd", "subscription_monthly", "subscription_yearly",
    "admin_add", "admin_bulk_add",
})


def get_tokens_remaining(db: Session, user_id: int) -> float:
    """Return tokens_remaining for user (0 if no row), rounded to 2 decimals. Uses raw SQL for reliability."""
    try:
        r = db.execute(
            text("SELECT tokens_remaining FROM user_token_balance WHERE user_id = :uid"),
            {"uid": user_id},
        ).fetchone()
        if r is not None and r[0] is not None:
            return round(max(0.0, float(r[0])), 2)
    except Exception:
        pass
    return 0.0


def subscription_invoice_already_processed(db: Session, user_id: int, stripe_invoice_id: str) -> bool:
    """
    Return True if we have already recorded a subscription token award for this Stripe invoice (idempotency for webhook retries).
    """
    if not stripe_invoice_id or not _has_token_ledger:
        return False
    if not _token_ledger_table_exists(db):
        return False
    try:
        r = db.execute(
            text("""
                SELECT 1 FROM token_ledger
                WHERE user_id = :uid AND activity_type = 'add'
                  AND reason IN ('subscription_monthly', 'subscription_yearly')
                  AND (metadata->>'stripe_invoice_id') = :inv_id
                LIMIT 1
            """),
            {"uid": user_id, "inv_id": stripe_invoice_id},
        ).fetchone()
        return r is not None
    except Exception:
        return False


def subscription_session_already_processed(db: Session, stripe_session_id: str) -> bool:
    """
    Return True if we have already recorded a subscription token award for this Stripe checkout session (idempotency).
    """
    if not stripe_session_id or not _has_token_ledger:
        return False
    if not _token_ledger_table_exists(db):
        return False
    try:
        r = db.execute(
            text("""
                SELECT 1 FROM token_ledger
                WHERE activity_type = 'add'
                  AND reason IN ('subscription_monthly', 'subscription_yearly')
                  AND (metadata->>'stripe_session_id') = :sid
                LIMIT 1
            """),
            {"sid": stripe_session_id},
        ).fetchone()
        return r is not None
    except Exception:
        return False


def try_register_checkout_session(db: Session, stripe_session_id: str) -> bool:
    """
    Register a checkout session for idempotency (one token award per session).
    Returns True if this is the first time we see this session_id (caller should add tokens).
    Returns False if already processed (duplicate/retry) or session_id empty — caller should skip.
    Uses table stripe_processed_checkout_sessions (session_id PRIMARY KEY) so duplicates get IntegrityError.
    """
    if not stripe_session_id or not stripe_session_id.strip():
        return False
    try:
        db.execute(
            text("INSERT INTO stripe_processed_checkout_sessions (session_id) VALUES (:sid)"),
            {"sid": stripe_session_id.strip()},
        )
        db.flush()
        return True
    except IntegrityError:
        return False
    except Exception:
        try:
            r = db.execute(
                text("SELECT 1 FROM information_schema.tables WHERE table_schema = 'public' AND table_name = 'stripe_processed_checkout_sessions'")
            ).fetchone()
            if not r:
                return not subscription_session_already_processed(db, stripe_session_id)
        except Exception:
            pass
        return False


def subscription_id_already_awarded(db: Session, user_id: int, stripe_subscription_id: str) -> bool:
    """
    Return True if we have already awarded tokens for this Stripe subscription (e.g. from checkout.session.completed).
    """
    if not stripe_subscription_id or not _has_token_ledger:
        return False
    if not _token_ledger_table_exists(db):
        return False
    try:
        r = db.execute(
            text("""
                SELECT 1 FROM token_ledger
                WHERE user_id = :uid AND activity_type = 'add'
                  AND reason IN ('subscription_monthly', 'subscription_yearly')
                  AND (metadata->>'stripe_subscription_id') = :sub_id
                LIMIT 1
            """),
            {"uid": user_id, "sub_id": stripe_subscription_id},
        ).fetchone()
        return r is not None
    except Exception:
        return False


def add_tokens(
    db: Session,
    user_id: int,
    amount: float,
    reason: str,
    extra: dict | None = None,
) -> float:
    """
    Add amount to user's balance (rounded to 2 decimals). If reason is in PURCHASED_REASONS, also add to purchased_tokens.
    Creates row if missing. extra is stored in token_ledger.metadata (e.g. {"stripe_invoice_id": "in_xxx"} for idempotency).
    Returns new tokens_remaining rounded to 2 decimals.
    """
    amount = round(float(amount), 2)
    if amount <= 0:
        return get_tokens_remaining(db, user_id)
    purchased_delta = amount if reason in PURCHASED_REASONS else 0.0
    try:
        db.execute(
            text("""
                INSERT INTO user_token_balance (user_id, tokens_remaining, purchased_tokens, last_gross_usd_used, updated_at)
                VALUES (:uid, :amt, :purchased, 0, NOW())
                ON CONFLICT (user_id) DO UPDATE SET
                tokens_remaining = user_token_balance.tokens_remaining + :amt,
                purchased_tokens = user_token_balance.purchased_tokens + :purchased,
                updated_at = NOW()
            """),
            {"uid": user_id, "amt": amount, "purchased": purchased_delta},
        )
        db.flush()
        if _has_token_ledger and _token_ledger_table_exists(db):
            db.add(models.TokenLedger(
                    user_id=user_id,
                    activity_type="add",
                    amount=amount,
                    reason=reason,
                    extra=extra,
                ))
            db.flush()
        return get_tokens_remaining(db, user_id)
    except Exception:
        try:
            db.execute(
                text("""
                    UPDATE user_token_balance
                    SET tokens_remaining = tokens_remaining + :amt,
                        purchased_tokens = purchased_tokens + :purchased,
                        updated_at = NOW()
                    WHERE user_id = :uid
                """),
                {"uid": user_id, "amt": amount, "purchased": purchased_delta},
            )
            db.flush()
            if _has_token_ledger and _token_ledger_table_exists(db):
                db.add(models.TokenLedger(
                    user_id=user_id,
                    activity_type="add",
                    amount=amount,
                    reason=reason,
                    extra=extra,
                ))
                db.flush()
        except Exception:
            pass
        return get_tokens_remaining(db, user_id)


def deduct_tokens(db: Session, user_id: int, amount: float) -> float:
    """
    Deduct amount from user's balance (amount rounded to 2 decimals). Balance never goes below 0.
    Returns new tokens_remaining rounded to 2 decimals.
    """
    amount = round(float(amount), 2)
    if amount <= 0:
        return get_tokens_remaining(db, user_id)
    try:
        db.execute(
            text("""
                UPDATE user_token_balance
                SET tokens_remaining = GREATEST(0, tokens_remaining - :amt),
                    updated_at = NOW()
                WHERE user_id = :uid
            """),
            {"uid": user_id, "amt": amount},
        )
        db.flush()
    except Exception:
        pass
    return get_tokens_remaining(db, user_id)


def purchased_tokens_for_referral(db: Session, user_id: int) -> float:
    """Return purchased_tokens for this user (referral burn logic)."""
    try:
        r = db.execute(
            text("SELECT purchased_tokens FROM user_token_balance WHERE user_id = :uid"),
            {"uid": user_id},
        ).fetchone()
        if r is not None and r[0] is not None:
            return max(0.0, float(r[0]))
    except Exception:
        pass
    return 0.0
