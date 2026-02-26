"""
Run bot_status migration for either PostgreSQL or SQLite.
Handles "column already exists" / "duplicate column name" so safe to run multiple times.

Usage (from project root):
  python migrations/run_bot_status_migration.py

Requires: DATABASE_URL in .env (e.g. postgresql://... or sqlite:///...).
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Load .env
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
        cur.execute("ALTER TABLE users ADD COLUMN IF NOT EXISTS bot_status VARCHAR(20) DEFAULT 'stopped'")
        print("PostgreSQL: bot_status column added or already exists.")
    finally:
        cur.close()
        conn.close()


def run_sqlite():
    import sqlite3
    # DATABASE_URL may be "sqlite:///path/to/db" or "sqlite:///./db.sqlite"
    path = DATABASE_URL.replace("sqlite:///", "").split("?")[0]
    if not path or path == "sqlite":
        path = "utrader.db"
    conn = sqlite3.connect(path)
    try:
        conn.execute("ALTER TABLE users ADD COLUMN bot_status VARCHAR(20) DEFAULT 'stopped'")
        conn.commit()
        print("SQLite: bot_status column added.")
    except sqlite3.OperationalError as e:
        if "duplicate column name" in str(e).lower():
            print("SQLite: bot_status column already exists (OK).")
        else:
            raise
    finally:
        conn.close()


def main():
    if "postgresql" in DATABASE_URL or "postgres" in DATABASE_URL:
        run_postgres()
    elif DATABASE_URL.startswith("sqlite"):
        run_sqlite()
    else:
        print("Unsupported DATABASE_URL scheme. Run the SQL manually; see migrations/add_bot_status_to_users.sql", file=sys.stderr)
        sys.exit(1)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(0 if main() == 0 else 1)
    except Exception as e:
        print(f"Migration failed: {e}", file=sys.stderr)
        sys.exit(1)
