"""Run add_bot_desired_state migration. Safe to run multiple times."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from database import engine
from sqlalchemy import text

def main():
    with engine.connect() as conn:
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS bot_desired_state VARCHAR(20) DEFAULT 'stopped'"))
        conn.commit()
        conn.execute(text("UPDATE users SET bot_desired_state = 'stopped' WHERE bot_desired_state IS NULL"))
        conn.commit()
    print("bot_desired_state migration done.")

if __name__ == "__main__":
    main()
