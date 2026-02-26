"""
Daily token deduction (post-Bitfinex API call at 10:15 UTC).

Uses daily_gross_profit_usd from user_profit_snapshot (stored at 09:40 UTC).
Formula: new_tokens_remaining = tokens_remaining - daily_gross_profit (1:1 USD);
if new_tokens_remaining < 0 set to 0; if daily_gross_profit <= 0 do not deduct.
"""
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

import models


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


def run_daily_token_deduction(db: Session) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """
    For each user with token balance and profit snapshot, deduct daily gross profit
    from tokens_remaining (1:1 USD), update last_gross_usd_used and updated_at.

    Returns (list of deduction log entries, error_message if failed).
    """
    log_entries: List[Dict[str, Any]] = []
    try:
        # Users who have both user_token_balance and user_profit_snapshot
        rows = (
            db.query(models.UserTokenBalance, models.UserProfitSnapshot)
            .join(
                models.UserProfitSnapshot,
                models.UserTokenBalance.user_id == models.UserProfitSnapshot.user_id,
            )
            .all()
        )
        now_utc = datetime.utcnow()
        for token_row, snap in rows:
            user_id = token_row.user_id
            daily_gross = getattr(snap, "daily_gross_profit_usd", None)
            if daily_gross is None:
                daily_gross = 0.0
            daily_gross = float(daily_gross)

            tokens_before = float(token_row.tokens_remaining or 0)
            new_tokens, should_deduct = apply_deduction_rule(tokens_before, daily_gross)
            if not should_deduct:
                continue

            tokens_deducted = daily_gross  # 1:1 USD per requirement

            token_row.tokens_remaining = new_tokens
            token_row.last_gross_usd_used = daily_gross
            token_row.updated_at = now_utc

            log_entries.append({
                "user_id": user_id,
                "gross_profit": daily_gross,
                "tokens_deducted": tokens_deducted,
                "tokens_remaining_before": tokens_before,
                "tokens_remaining_after": new_tokens,
                "timestamp": now_utc.isoformat() + "Z",
            })
        db.commit()
        return log_entries, None
    except Exception as e:
        db.rollback()
        return log_entries, str(e)
