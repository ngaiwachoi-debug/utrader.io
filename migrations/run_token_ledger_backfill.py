"""
Backfill total_tokens_added and total_tokens_deducted from existing user_token_balance and user_profit_snapshot.
Inserts one token_ledger row per user (reason=migration_backfill).
Run once after add_token_ledger_and_balance_columns.sql.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
from sqlalchemy import text


def main():
    db = SessionLocal()
    try:
        r = db.execute(text("SELECT 1 FROM information_schema.tables WHERE table_name = 'token_ledger'")).fetchone()
        if not r:
            print("Run add_token_ledger_and_balance_columns.sql first.")
            return

        # Skip users already backfilled (idempotent)
        rows = db.execute(text("""
            SELECT b.user_id, b.tokens_remaining, b.purchased_tokens,
                   s.gross_profit_usd
            FROM user_token_balance b
            LEFT JOIN user_profit_snapshot s ON s.user_id = b.user_id
            WHERE NOT EXISTS (
                SELECT 1 FROM token_ledger l
                WHERE l.user_id = b.user_id AND l.reason = 'migration_backfill'
            )
        """)).fetchall()

        for row in rows:
            user_id, tokens_remaining, purchased_tokens, gross_profit_usd = row
            tr = float(tokens_remaining or 0)
            total_tokens_deducted = int(float(gross_profit_usd or 0) * 10)
            total_tokens_added = tr + total_tokens_deducted
            purchased_added = float(purchased_tokens or 0)

            db.execute(
                text("""
                    UPDATE user_token_balance
                    SET total_tokens_added = :added, total_tokens_deducted = :deducted,
                        purchased_tokens_added = :purchased
                    WHERE user_id = :uid
                """),
                {"added": total_tokens_added, "deducted": total_tokens_deducted, "purchased": purchased_added, "uid": user_id},
            )
            db.execute(
                text("""
                    INSERT INTO token_ledger (user_id, activity_type, amount, reason, metadata)
                    VALUES (:uid, 'add', :amount, 'migration_backfill', '{"note": "initial"}'::jsonb)
                """),
                {"uid": user_id, "amount": total_tokens_added},
            )
        db.commit()
        print(f"Backfilled {len(rows)} user_token_balance rows and inserted token_ledger rows.")
    except Exception as e:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
