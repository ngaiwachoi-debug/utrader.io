"""Check token_ledger for subscription (plan) purchases for a user. Run from project root: python scripts/check_plan_purchase_record.py [user_id]"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database import SessionLocal


def main():
    user_id = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    db = SessionLocal()
    try:
        # Subscription adds only
        rows = db.execute(
            text("""
                SELECT id, user_id, amount, reason, created_at, metadata
                FROM token_ledger
                WHERE user_id = :uid
                  AND activity_type = 'add'
                  AND reason IN ('subscription_monthly', 'subscription_yearly')
                ORDER BY created_at DESC
            """),
            {"uid": user_id},
        ).fetchall()
        print(f"User {user_id} – subscription token adds (plan purchases):")
        if not rows:
            print("  (none)")
        else:
            for r in rows:
                print(f"  id={r[0]} amount={r[2]} reason={r[3]} created_at={r[4]} metadata={r[5]}")
        # Balance
        bal = db.execute(
            text("SELECT tokens_remaining, purchased_tokens FROM user_token_balance WHERE user_id = :uid"),
            {"uid": user_id},
        ).fetchone()
        if bal:
            print(f"user_token_balance: tokens_remaining={bal[0]} purchased_tokens={bal[1]}")
        else:
            print("user_token_balance: (no row)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
