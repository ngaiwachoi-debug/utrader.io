"""
Read-only check: why would user_id=2 be skipped by run_daily_token_deduction?
Uses same join and logic as services/daily_token_deduction.py without changing any data.
Usage: python scripts/check_deduction_eligibility_user2.py [user_id]
"""
import os
import sys
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

def main():
    user_id = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    import database
    import models
    from services.daily_token_deduction import apply_deduction_rule

    db = database.SessionLocal()
    try:
        # Same query as run_daily_token_deduction (no user_ids filter => all users, then we filter by user_id for report)
        q = (
            db.query(models.UserTokenBalance, models.UserProfitSnapshot, models.User)
            .join(
                models.UserProfitSnapshot,
                models.UserTokenBalance.user_id == models.UserProfitSnapshot.user_id,
            )
            .join(models.User, models.User.id == models.UserTokenBalance.user_id)
            .filter(models.UserTokenBalance.user_id == user_id)
        )
        rows = q.all()
        now_utc = datetime.utcnow()
        date_utc = now_utc.date() if hasattr(now_utc, "date") else date(now_utc.year, now_utc.month, now_utc.day)

        print(f"=== Deduction eligibility check for user_id={user_id} (UTC date_utc={date_utc}) ===\n")

        if not rows:
            print("NOT IN DEDUCTION QUERY: No row for this user in the join of user_token_balance + user_profit_snapshot + users.")
            print("  -> User is never considered for deduction until they have both:")
            print("     - user_token_balance row")
            print("     - user_profit_snapshot row")
            return 0

        token_row, snap, user = rows[0]
        email = getattr(user, "email", None) or ""
        last_ded = getattr(snap, "last_deduction_processed_date", None)
        daily_gross = getattr(snap, "daily_gross_profit_usd", None)
        if daily_gross is None:
            daily_gross = 0.0
        daily_gross = float(daily_gross)
        tokens_before = float(token_row.tokens_remaining or 0)
        new_tokens, should_deduct = apply_deduction_rule(tokens_before, daily_gross)

        print("IN DEDUCTION QUERY: User is in the join.")
        print(f"  email: {email}")
        print(f"  user_token_balance.tokens_remaining: {tokens_before}")
        print(f"  user_profit_snapshot.daily_gross_profit_usd: {daily_gross}")
        print(f"  user_profit_snapshot.last_deduction_processed_date: {last_ded}")
        print(f"  user_profit_snapshot.gross_profit_usd: {getattr(snap, 'gross_profit_usd', None)}")
        print(f"  user_profit_snapshot.updated_at: {getattr(snap, 'updated_at', None)}")
        print()

        if last_ded == date_utc:
            print("SKIP: last_deduction_processed_date == today -> already processed (no double-charge).")
            return 0
        if daily_gross <= 0:
            print("SKIP: daily_gross_profit_usd <= 0 -> nothing to deduct.")
            print("  (Only the 10:00 UTC job or 09:00 cache at 10:30 / 11:15 catch-up sets daily_gross_profit_usd.)")
            return 0
        if not should_deduct:
            print("SKIP: apply_deduction_rule returned should_deduct=False.")
            return 0

        print("WOULD DEDUCT: All checks pass. Deduction would run for this user.")
        print(f"  tokens_deducted would be: {daily_gross} (1:1 USD)")
        print(f"  tokens_remaining after would be: {new_tokens}")
        return 0
    finally:
        db.close()

if __name__ == "__main__":
    sys.exit(main())
