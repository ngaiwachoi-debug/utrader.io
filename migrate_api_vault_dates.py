"""
Add created_at and last_tested_at to api_vault if they don't exist.
Run once: python migrate_api_vault_dates.py
"""
from sqlalchemy import text
from database import engine

def run():
    with engine.connect() as conn:
        for col, typ in [
            ("created_at", "TIMESTAMP"),
            ("last_tested_at", "TIMESTAMP"),
            ("last_test_balance", "DOUBLE PRECISION"),
        ]:
            try:
                if "postgresql" in str(engine.url):
                    conn.execute(text(f"ALTER TABLE api_vault ADD COLUMN IF NOT EXISTS {col} {typ}"))
                else:
                    conn.execute(text(f"ALTER TABLE api_vault ADD COLUMN {col} {typ}"))
                conn.commit()
                print(f"Added column {col} (or already exists)")
            except Exception as e:
                if "already exists" in str(e).lower() or "duplicate" in str(e).lower():
                    print(f"Column {col} already exists")
                else:
                    print(f"Column {col}: {e}")
                conn.rollback()

if __name__ == "__main__":
    run()
    print("Done.")
