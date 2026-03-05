"""Run token_ledger migration. Run from project root: python scripts/run_token_ledger_migration.py"""
import os
import sys
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)
os.chdir(_root)
from dotenv import load_dotenv
load_dotenv(os.path.join(_root, ".env"))

from sqlalchemy import text
from database import SessionLocal

def main():
    db = SessionLocal()
    try:
        for label, stmt in [
            ("token_ledger table", "CREATE TABLE IF NOT EXISTS token_ledger (id SERIAL PRIMARY KEY, user_id INTEGER NOT NULL REFERENCES users(id), activity_type VARCHAR(16) NOT NULL, amount DOUBLE PRECISION NOT NULL, reason VARCHAR(64) NOT NULL, created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(), metadata JSONB)"),
            ("token_ledger index", "CREATE INDEX IF NOT EXISTS idx_token_ledger_user_id_created_at ON token_ledger(user_id, created_at)"),
        ]:
            try:
                db.execute(text(stmt))
                db.commit()
                print(f"OK: {label}")
            except Exception as e:
                if "already exists" in str(e):
                    print(f"Skip (exists): {label}")
                    db.rollback()
                else:
                    db.rollback()
                    raise
        for col in ["total_tokens_added", "total_tokens_deducted", "purchased_tokens_added"]:
            try:
                db.execute(text(f"ALTER TABLE user_token_balance ADD COLUMN IF NOT EXISTS {col} DOUBLE PRECISION NOT NULL DEFAULT 0"))
                db.commit()
                print(f"OK: user_token_balance.{col}")
            except Exception as e:
                if "already exists" in str(e) or "duplicate" in str(e).lower():
                    print(f"Skip (exists): user_token_balance.{col}")
                    db.rollback()
                else:
                    db.rollback()
                    raise
        print("Migration done.")
    finally:
        db.close()

if __name__ == "__main__":
    main()
