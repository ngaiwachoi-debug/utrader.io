"""
Set choiwangai@gmail.com's API vault created_at to 10 days ago
so gross profit is computed from that registration date.
Run once: python scripts/set_registration_10_days_ago.py
"""
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
import models

EMAIL = "choiwangai@gmail.com"
DAYS_AGO = 10


def main():
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == EMAIL).first()
        if not user:
            print(f"User not found: {EMAIL}")
            return 1
        vault = db.query(models.APIVault).filter(models.APIVault.user_id == user.id).first()
        if not vault:
            print(f"No vault for {EMAIL}")
            return 1
        new_date = datetime.utcnow() - timedelta(days=DAYS_AGO)
        vault.created_at = new_date
        db.commit()
        print(f"Set {EMAIL} (user_id={user.id}) vault.created_at to {new_date.isoformat()} ({DAYS_AGO} days ago)")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(0 if main() == 0 else 1)
