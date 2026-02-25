"""
One-off migration: add missing columns to users table if they don't exist.
Fixes: column users.plan_tier does not exist (and any other missing model columns).
"""
from sqlalchemy import text
from database import engine

# (column_name, sql_type_with_default)
USER_COLUMNS = [
    ("plan_tier", "VARCHAR DEFAULT 'trial'"),
    ("lending_limit", "FLOAT DEFAULT 250000"),
    ("rebalance_interval", "INTEGER DEFAULT 3"),
    ("pro_expiry", "TIMESTAMP"),
    ("referral_code", "VARCHAR"),
    ("referred_by", "INTEGER"),
    ("status", "VARCHAR DEFAULT 'active'"),
]

def main():
    with engine.connect() as conn:
        for col_name, col_def in USER_COLUMNS:
            try:
                if engine.dialect.name == "postgresql":
                    conn.execute(text(
                        f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col_name} {col_def}"
                    ))
                else:
                    conn.execute(text(f"ALTER TABLE users ADD COLUMN {col_name} {col_def}"))
                conn.commit()
                print(f"Added column: {col_name}")
            except Exception as e:
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    print(f"Column {col_name} already exists, skip")
                else:
                    print(f"Column {col_name}: {e}")
                conn.rollback()
    print("Migration done.")

if __name__ == "__main__":
    main()
