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
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

import models
from services.referral_rewards import apply_referral_rewards
from services import token_ledger_service as token_ledger_svc

TOKENS_PER_USDT_GROSS = 10  # used_tokens = gross_profit_usd × TOKENS_PER_USDT_GROSS (documented for consistency)


def apply_deduction_rule(tokens_remaining: float, daily_gross_profit: float) -> Tuple[float, bool]:
    """
    Pure deduction rule for one user.
    Returns (new_tokens_remaining, should_deduct).
    If daily_gross_profit <= 0, should_deduct is False and tokens unchanged.
    """
    if daily_gross_profit <= 0:
        return tokens_remaining, False
    new_raw = tokens_remaining - daily_gross_profit
    return max(0.0, new_raw), True


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
        now_utc = datetime.utcnow()
        date_utc = now_utc.date() if hasattr(now_utc, "date") else date(now_utc.year, now_utc.month, now_utc.day)
        for token_row, snap, user in rows:
            user_id = token_row.user_id
            if getattr(snap, "last_deduction_processed_date", None) == date_utc:
                continue  # already processed (prevent double-charge)
            email = getattr(user, "email", None) or ""
            daily_gross = getattr(snap, "daily_gross_profit_usd", None)
            if daily_gross is None:
                daily_gross = 0.0
            daily_gross = float(daily_gross)

            tokens_before = float(token_row.tokens_remaining or 0)
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
                "tokens_remaining_after": new_tokens,
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
                    tokens_remaining_after=new_tokens,
                    account_switch_note=account_switch_note,
                ))
            if getattr(snap, "account_switch_note", None) is not None:
                snap.account_switch_note = None
            if hasattr(snap, "deduction_processed"):
                snap.deduction_processed = True
            if hasattr(snap, "last_deduction_processed_date"):
                snap.last_deduction_processed_date = date_utc

        db.commit()
        return log_entries, None
    except Exception as e:
        db.rollback()
        return log_entries, str(e)
