"""
Add purchased_tokens column to user_token_balance.
Run once: python migrate_add_purchased_tokens.py
"""
import os
import sqlite3

DB_PATH = os.getenv("DATABASE_URL", "sqlite:///./utrader.db").replace("sqlite:///", "")


def main():
    if not os.path.exists(DB_PATH):
        print(f"DB not found: {DB_PATH}")
        return
    conn = sqlite3.connect(DB_PATH)
    try:
        cur = conn.execute("PRAGMA table_info(user_token_balance)")
        cols = [r[1] for r in cur.fetchall()]
        if "purchased_tokens" in cols:
            print("purchased_tokens already exists")
            return
        conn.execute("ALTER TABLE user_token_balance ADD COLUMN purchased_tokens REAL DEFAULT 0")
        conn.commit()
        print("Added purchased_tokens column")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
