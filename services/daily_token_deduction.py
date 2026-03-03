"""
Daily token deduction at 10:30 UTC (30-min buffer after 10:00 UTC API fetch). No Bitfinex API call here.

Uses daily_gross_profit_usd from user_profit_snapshot (stored at 10:00 UTC, optional retry at 10:10).
Formula: new_tokens_remaining = tokens_remaining - daily_gross_profit (1:1 USD);
if new_tokens_remaining < 0 set to 0; if daily_gross_profit <= 0 do not deduct.

Used tokens (display): used_tokens = int(gross_profit_usd × TOKENS_PER_USDT_GROSS) with TOKENS_PER_USDT_GROSS = 10.
Example: choiwangai@gmail.com gross_profit_usd = 72.20 → used_tokens = 722.
Referral: only purchased tokens (not free 150) trigger L1/L2/L3 USDT Credit rewards.
We consume free tokens first; purchased_burned = max(0, daily_gross - free_remaining).
"""
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional, Tuple


def _utc_today() -> date:
    """Today's date in UTC (for deduction date comparison; avoids server TZ issues)."""
    return datetime.now(timezone.utc).date()

from sqlalchemy.orm import Session

import logging

import models
from services.referral_rewards import apply_referral_rewards
from services import token_ledger_service as token_ledger_svc

_log = logging.getLogger(__name__)

TOKENS_PER_USDT_GROSS = 10  # used_tokens = gross_profit_usd × TOKENS_PER_USDT_GROSS (documented for consistency)


def apply_deduction_rule(tokens_remaining: float, daily_gross_profit: float) -> Tuple[float, bool]:
    """
    Pure deduction rule for one user.
    Returns (new_tokens_remaining, should_deduct), rounded to 2 decimals.
    If daily_gross_profit <= 0, should_deduct is False and tokens unchanged.
    """
    if daily_gross_profit <= 0:
        return round(float(tokens_remaining), 2), False
    new_raw = tokens_remaining - daily_gross_profit
    return round(max(0.0, new_raw), 2), True


def run_deduction_for_user_for_date(
    db: Session,
    user_id: int,
    date_d: date,
    daily_gross: float,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Deduct tokens for one user for a specific date (manual-trigger backfill of missed days).
    If already deducted for date_d or daily_gross <= 0, returns (None, None). Does not commit.
    """
    q = (
        db.query(models.UserTokenBalance, models.UserProfitSnapshot, models.User)
        .join(
            models.UserProfitSnapshot,
            models.UserTokenBalance.user_id == models.UserProfitSnapshot.user_id,
        )
        .join(models.User, models.User.id == models.UserTokenBalance.user_id)
        .filter(models.UserTokenBalance.user_id == user_id)
    )
    row = q.first()
    if not row:
        return None, None
    token_row, snap, user = row
    if getattr(snap, "last_deduction_processed_date", None) == date_d:
        return None, None
    if daily_gross <= 0:
        return None, None
    email = getattr(user, "email", None) or ""
    tokens_before = round(float(token_row.tokens_remaining or 0), 2)
    new_tokens, should_deduct = apply_deduction_rule(tokens_before, daily_gross)
    if not should_deduct:
        return None, None
    tokens_deducted = round(float(daily_gross), 2)
    now_utc = datetime.utcnow()
    purchased_added = token_ledger_svc.purchased_tokens_for_referral(db, user_id)
    free_remaining = max(0.0, tokens_before - purchased_added)
    purchased_burned = max(0.0, daily_gross - free_remaining)
    if purchased_burned > 0:
        apply_referral_rewards(db, user_id, purchased_burned)
    new_tokens = token_ledger_svc.deduct_tokens(db, user_id, tokens_deducted)
    token_row.last_gross_usd_used = daily_gross
    token_row.updated_at = now_utc
    gross_profit_usd = float(getattr(snap, "gross_profit_usd", None) or 0)
    total_used_tokens = int(gross_profit_usd * TOKENS_PER_USDT_GROSS) if gross_profit_usd else 0
    account_switch_note = getattr(snap, "account_switch_note", None)
    log_entry = {
        "user_id": user_id,
        "email": email,
        "gross_profit": round(daily_gross, 2),
        "tokens_deducted": tokens_deducted,
        "tokens_remaining_before": tokens_before,
        "tokens_remaining_after": round(new_tokens, 2),
        "timestamp": now_utc.isoformat() + "Z",
        "total_used_tokens": total_used_tokens,
        "account_switch_note": account_switch_note,
        "for_date": date_d.isoformat(),
    }
    if hasattr(models, "DeductionLog"):
        db.add(models.DeductionLog(
            user_id=user_id,
            email=email or None,
            timestamp_utc=now_utc,
            daily_gross_profit_usd=daily_gross,
            tokens_deducted=tokens_deducted,
            total_used_tokens=float(total_used_tokens),
            tokens_remaining_after=round(new_tokens, 2),
            account_switch_note=account_switch_note,
        ))
    if getattr(snap, "account_switch_note", None) is not None:
        snap.account_switch_note = None
    if hasattr(snap, "deduction_processed"):
        snap.deduction_processed = True
    if hasattr(snap, "last_deduction_processed_date"):
        snap.last_deduction_processed_date = date_d
    return log_entry, None


def run_daily_token_deduction(
    db: Session,
    user_ids: Optional[List[int]] = None,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    For each user with token balance and profit snapshot, deduct daily gross profit
    from tokens_remaining (1:1 USD), update last_gross_usd_used and updated_at.
    Persists each deduction to deduction_log (with email and account_switch_note).
    If user_ids is provided, only those users are processed (e.g. 11:15 catch-up).

    Returns (list of deduction log entries, error_message if failed).
    """
    log_entries: List[Dict[str, Any]] = []
    try:
        q = (
            db.query(models.UserTokenBalance, models.UserProfitSnapshot, models.User)
            .join(
                models.UserProfitSnapshot,
                models.UserTokenBalance.user_id == models.UserProfitSnapshot.user_id,
            )
            .join(models.User, models.User.id == models.UserTokenBalance.user_id)
        )
        if user_ids is not None:
            q = q.filter(models.UserTokenBalance.user_id.in_(user_ids))
        rows = q.all()
        now_utc = datetime.now(timezone.utc)
        date_utc = _utc_today()
        skipped_already_processed = 0
        for token_row, snap, user in rows:
            user_id = token_row.user_id
            if getattr(snap, "last_deduction_processed_date", None) == date_utc:
                skipped_already_processed += 1
                continue  # already processed (prevent double-charge)
            email = getattr(user, "email", None) or ""
            daily_gross = getattr(snap, "daily_gross_profit_usd", None)
            if daily_gross is None:
                daily_gross = 0.0
            daily_gross = round(float(daily_gross), 2)

            tokens_before = round(float(token_row.tokens_remaining or 0), 2)
            new_tokens, should_deduct = apply_deduction_rule(tokens_before, daily_gross)
            if not should_deduct:
                continue

            tokens_deducted = daily_gross  # 1:1 USD per requirement

            purchased_added = token_ledger_svc.purchased_tokens_for_referral(db, user_id)
            free_remaining = max(0.0, tokens_before - purchased_added)
            purchased_burned = max(0.0, daily_gross - free_remaining)
            if purchased_burned > 0:
                apply_referral_rewards(db, user_id, purchased_burned)

            new_tokens = token_ledger_svc.deduct_tokens(db, user_id, tokens_deducted)
            token_row.last_gross_usd_used = daily_gross
            token_row.updated_at = now_utc

            gross_profit_usd = float(getattr(snap, "gross_profit_usd", None) or 0)
            total_used_tokens = int(gross_profit_usd * TOKENS_PER_USDT_GROSS) if gross_profit_usd else 0
            account_switch_note = getattr(snap, "account_switch_note", None)

            log_entries.append({
                "user_id": user_id,
                "email": email,
                "gross_profit": daily_gross,
                "tokens_deducted": tokens_deducted,
                "tokens_remaining_before": tokens_before,
                "tokens_remaining_after": round(new_tokens, 2),
                "timestamp": now_utc.isoformat() + "Z",
                "total_used_tokens": total_used_tokens,
                "account_switch_note": account_switch_note,
            })

            if hasattr(models, "DeductionLog"):
                db.add(models.DeductionLog(
                    user_id=user_id,
                    email=email or None,
                    timestamp_utc=now_utc,
                    daily_gross_profit_usd=daily_gross,
                    tokens_deducted=tokens_deducted,
                    total_used_tokens=float(total_used_tokens),
                    tokens_remaining_after=round(new_tokens, 2),
                    account_switch_note=account_switch_note,
                ))
            if getattr(snap, "account_switch_note", None) is not None:
                snap.account_switch_note = None
            if hasattr(snap, "deduction_processed"):
                snap.deduction_processed = True
            if hasattr(snap, "last_deduction_processed_date"):
                snap.last_deduction_processed_date = date_utc

        db.commit()
        if skipped_already_processed or log_entries:
            _log.info(
                "run_daily_token_deduction date_utc=%s skipped_already_processed=%d deducted=%d",
                date_utc, skipped_already_processed, len(log_entries),
            )
        return log_entries, None
    except Exception as e:
        db.rollback()
        return log_entries, str(e)
