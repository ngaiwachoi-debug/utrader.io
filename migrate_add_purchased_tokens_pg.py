"""
Add purchased_tokens column to user_token_balance (PostgreSQL).
Run once: python migrate_add_purchased_tokens_pg.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import engine
from sqlalchemy import text


def main():
    with engine.connect() as conn:
        # Check if column exists (PostgreSQL)
        r = conn.execute(
            text(
                """
            SELECT column_name FROM information_schema.columns
            WHERE table_name = 'user_token_balance' AND column_name = 'purchased_tokens'
            """
            )
        )
        if r.fetchone():
            print("purchased_tokens already exists")
            return
        conn.execute(
            text("ALTER TABLE user_token_balance ADD COLUMN purchased_tokens DOUBLE PRECISION DEFAULT 0")
        )
        conn.commit()
        print("Added purchased_tokens column to user_token_balance")


if __name__ == "__main__":
    main()
