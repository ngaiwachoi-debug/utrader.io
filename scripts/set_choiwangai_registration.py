"""
One-off: set choiwangai@gmail.com vault created_at to 2026-02-22 09:30 (UTC).
- Registration must be earlier than the earliest ledger data (e.g. 2026-02-23 09:30).
- Gross Profit filters ledger entries to the window [registration, latest order];
  with this date and latest order 2026-02-26 09:30, the four Margin Funding Payment
  entries sum to ~68.93–69.03.
Run from project root: python scripts/set_choiwangai_registration.py
"""
import sys
from pathlib import Path
from datetime import datetime

# Add project root for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import SessionLocal
import models

REGISTRATION_DT = datetime(2026, 2, 22, 9, 30, 0)  # UTC
EMAIL = "choiwangai@gmail.com"


def main():
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == EMAIL).first()
        if not user:
            print(f"User not found: {EMAIL}")
            return 1
        vault = db.query(models.APIVault).filter(models.APIVault.user_id == user.id).first()
        if not vault:
            print(f"No vault for {EMAIL}. Connect API keys first.")
            return 1
        vault.created_at = REGISTRATION_DT
        db.commit()
        print(f"Set vault created_at to {REGISTRATION_DT} for {EMAIL} (user_id={user.id})")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
