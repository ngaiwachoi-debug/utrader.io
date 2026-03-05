"""
Create admin-related tables: user_usdt_credit, usdt_history, withdrawal_requests,
admin_notifications, admin_settings, admin_audit_log. Add users.created_at if missing.
PostgreSQL. Run once: python migrate_admin_tables.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from database import engine
from sqlalchemy import text


def main():
    with engine.connect() as conn:
        # users.created_at
        try:
            conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW()"))
            conn.commit()
        except Exception as e:
            if "already exists" not in str(e).lower():
                print("users.created_at:", e)
            conn.rollback()

        # user_usdt_credit
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS user_usdt_credit (
                user_id INTEGER PRIMARY KEY REFERENCES users(id),
                usdt_credit DOUBLE PRECISION DEFAULT 0,
                total_earned DOUBLE PRECISION DEFAULT 0,
                total_withdrawn DOUBLE PRECISION DEFAULT 0,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.commit()

        # usdt_history
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS usdt_history (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                amount DOUBLE PRECISION NOT NULL,
                reason VARCHAR(64),
                created_at TIMESTAMP DEFAULT NOW(),
                admin_email VARCHAR(255)
            )
        """))
        conn.commit()

        # withdrawal_requests
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS withdrawal_requests (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL REFERENCES users(id),
                amount DOUBLE PRECISION NOT NULL,
                address VARCHAR(255) NOT NULL,
                status VARCHAR(32) DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT NOW(),
                processed_at TIMESTAMP,
                processed_by VARCHAR(255)
            )
        """))
        conn.commit()

        # admin_notifications
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS admin_notifications (
                id SERIAL PRIMARY KEY,
                title VARCHAR(255) NOT NULL,
                content TEXT,
                type VARCHAR(32) DEFAULT 'info',
                target_user_id INTEGER REFERENCES users(id),
                created_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.commit()

        # admin_settings
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS admin_settings (
                key VARCHAR(128) PRIMARY KEY,
                value TEXT,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """))
        conn.commit()

        # admin_audit_log
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS admin_audit_log (
                id SERIAL PRIMARY KEY,
                ts TIMESTAMP NOT NULL DEFAULT NOW(),
                email VARCHAR(255) NOT NULL,
                action VARCHAR(64) NOT NULL,
                detail TEXT
            )
        """))
        conn.commit()

        # Seed default admin settings
        defaults = [
            ("registration_bonus_tokens", "150"),
            ("min_withdrawal_usdt", "10"),
            ("daily_deduction_utc_hour", "10"),
            ("deduction_multiplier", "1"),
            ("referral_purchase_l1_pct", "10"),
            ("referral_purchase_l2_pct", "5"),
            ("referral_purchase_l3_pct", "2"),
            ("bot_auto_start", "true"),
            ("referral_system_enabled", "true"),
            ("withdrawal_enabled", "true"),
            ("maintenance_mode", "false"),
        ]
        for k, v in defaults:
            conn.execute(
                text("INSERT INTO admin_settings (key, value) VALUES (:k, :v) ON CONFLICT (key) DO NOTHING"),
                {"k": k, "v": v},
            )
        conn.commit()

    print("Admin tables migration done.")


if __name__ == "__main__":
    main()
