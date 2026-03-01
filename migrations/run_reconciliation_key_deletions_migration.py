"""
Add users.key_deletions and user_profit_snapshot.reconciliation_completed if missing.
Safe to run multiple times (IF NOT EXISTS).

Usage (from project root):
  python migrations/run_reconciliation_key_deletions_migration.py

Requires: DATABASE_URL in .env.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

DATABASE_URL = os.getenv("DATABASE_URL", "")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set in .env", file=sys.stderr)
    sys.exit(1)


def run_postgres():
    import psycopg2
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()
    try:
        cur.execute("ALTER TABLE user_profit_snapshot ADD COLUMN IF NOT EXISTS reconciliation_completed BOOLEAN DEFAULT TRUE")
        print("PostgreSQL: user_profit_snapshot.reconciliation_completed added or already exists.")
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS key_deletions TEXT DEFAULT '{}'")
        print("PostgreSQL: users.key_deletions added or already exists.")
    finally:
        cur.close()
        conn.close()


def main():
    if "postgresql" in DATABASE_URL or "postgres" in DATABASE_URL:
        run_postgres()
    else:
        print("Unsupported DATABASE_URL. Run migrations/add_reconciliation_completed_and_key_deletions.sql manually.", file=sys.stderr)
        sys.exit(1)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(0 if main() == 0 else 1)
    except Exception as e:
        print(f"Migration failed: {e}", file=sys.stderr)
        sys.exit(1)
