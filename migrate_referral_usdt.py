"""
Migration: 3-level referral + USDT withdrawal enhancements.
- users.usdt_withdraw_address (VARCHAR 255)
- withdrawal_requests.rejection_note (VARCHAR 500)
- referral_rewards table
- Default min_withdrawal_usdt = 1 (spec); keep existing if set
Run once: python migrate_referral_usdt.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import engine
from sqlalchemy import text


def main():
    with engine.connect() as conn:
        # users.usdt_withdraw_address
        try:
            conn.execute(text(
                "ALTER TABLE users ADD COLUMN IF NOT EXISTS usdt_withdraw_address VARCHAR(255)"
            ))
            conn.commit()
            print("Added users.usdt_withdraw_address")
        except Exception as e:
            if "already exists" not in str(e).lower():
                print("usdt_withdraw_address:", e)
            conn.rollback()

        # withdrawal_requests.rejection_note
        try:
            conn.execute(text(
                "ALTER TABLE withdrawal_requests ADD COLUMN IF NOT EXISTS rejection_note VARCHAR(500)"
            ))
            conn.commit()
            print("Added withdrawal_requests.rejection_note")
        except Exception as e:
            if "already exists" not in str(e).lower():
                print("rejection_note:", e)
            conn.rollback()

        # referral_rewards
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS referral_rewards (
                id SERIAL PRIMARY KEY,
                burning_user_id INTEGER NOT NULL REFERENCES users(id),
                level_1_id INTEGER REFERENCES users(id),
                level_2_id INTEGER REFERENCES users(id),
                level_3_id INTEGER REFERENCES users(id),
                reward_l1 DOUBLE PRECISION NOT NULL DEFAULT 0,
                reward_l2 DOUBLE PRECISION NOT NULL DEFAULT 0,
                reward_l3 DOUBLE PRECISION NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.commit()
        print("Created referral_rewards table")

        # Optional: set min_withdrawal_usdt to 1 if not present (spec default)
        try:
            conn.execute(text("""
                INSERT INTO admin_settings (key, value) VALUES ('min_withdrawal_usdt', '1')
                ON CONFLICT (key) DO NOTHING
            """))
            conn.commit()
        except Exception:
            conn.rollback()

    print("Migration done.")


if __name__ == "__main__":
    main()
