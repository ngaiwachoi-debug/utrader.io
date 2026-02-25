"""
Clear all free trial records from the trial_history table.
After running, any Bitfinex account can connect and use the free trial again.

Run from project root:
  python scripts/clear_trial_history.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import SessionLocal
import models

def main():
    db = SessionLocal()
    try:
        deleted = db.query(models.TrialHistory).delete()
        db.commit()
        print(f"Cleared {deleted} free trial record(s). Bitfinex accounts can connect and use the trial again.")
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    main()
