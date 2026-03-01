"""
Balance-only token service. Single source of truth: user_token_balance.tokens_remaining.
No ledger table; all reads/writes use tokens_remaining and purchased_tokens.
"""
from sqlalchemy.orm import Session
from sqlalchemy import text

PURCHASED_REASONS = frozenset({
    "deposit_usd", "subscription_monthly", "subscription_yearly",
    "admin_add", "admin_bulk_add",
})


def get_tokens_remaining(db: Session, user_id: int) -> float:
    """Return tokens_remaining for user (0 if no row). Uses raw SQL for reliability."""
    try:
        r = db.execute(
            text("SELECT tokens_remaining FROM user_token_balance WHERE user_id = :uid"),
            {"uid": user_id},
        ).fetchone()
        if r is not None and r[0] is not None:
            return max(0.0, float(r[0]))
    except Exception:
        pass
    return 0.0


def add_tokens(
    db: Session,
    user_id: int,
    amount: float,
    reason: str,
) -> float:
    """
    Add amount to user's balance. If reason is in PURCHASED_REASONS, also add to purchased_tokens.
    Creates row if missing. Returns new tokens_remaining. Uses raw SQL only (no balance-row check).
    """
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
        except Exception:
            pass
        return get_tokens_remaining(db, user_id)


def deduct_tokens(db: Session, user_id: int, amount: float) -> float:
    """
    Deduct amount from user's balance. Balance never goes below 0.
    Returns new tokens_remaining.
    """
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
