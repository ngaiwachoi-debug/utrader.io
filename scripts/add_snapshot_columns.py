"""
Add last_trade_mts and total_trades_count to user_profit_snapshot for incremental gross profit sync.
Run once: python scripts/add_snapshot_columns.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from sqlalchemy import text
from database import engine


def main():
    with engine.connect() as conn:
        for col, typ in [("last_trade_mts", "BIGINT"), ("total_trades_count", "INTEGER")]:
            try:
                if engine.dialect.name == "postgresql":
                    conn.execute(text(f"ALTER TABLE user_profit_snapshot ADD COLUMN IF NOT EXISTS {col} {typ}"))
                else:
                    conn.execute(text(f"ALTER TABLE user_profit_snapshot ADD COLUMN {col} {typ}"))
                conn.commit()
                print(f"Added column {col}")
            except Exception as e:
                if "duplicate" in str(e).lower() or "already exists" in str(e).lower():
                    print(f"Column {col} already exists")
                else:
                    print(f"Column {col}: {e}")
    return 0


if __name__ == "__main__":
    sys.exit(0 if main() == 0 else 1)
