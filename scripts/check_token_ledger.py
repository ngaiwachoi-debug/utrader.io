"""Quick check of token_ledger table. Run from project root: python scripts/check_token_ledger.py"""
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from database import SessionLocal

def main():
    db = SessionLocal()
    try:
        r = db.execute(text("SELECT COUNT(*) FROM token_ledger")).scalar()
        print(f"token_ledger total rows: {r}")
        r2 = db.execute(text("SELECT COUNT(*) FROM token_ledger WHERE activity_type = 'add'")).scalar()
        print(f"token_ledger activity_type='add': {r2}")
        rows = db.execute(text("SELECT id, user_id, activity_type, amount, reason, created_at FROM token_ledger ORDER BY created_at DESC LIMIT 10")).fetchall()
        print("Latest 10 rows:")
        for row in rows:
            print(f"  id={row[0]} user_id={row[1]} type={row[2]} amount={row[3]} reason={row[4]} created_at={row[5]}")
    finally:
        db.close()

if __name__ == "__main__":
    main()
