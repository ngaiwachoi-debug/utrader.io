"""
Add purchased tokens for a user by email.
Usage (from project root):
  python scripts/add_tokens_for_email.py <email> <amount>
  python scripts/add_tokens_for_email.py choiwangai@gmail.com 1500
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
import models
from services import token_ledger_service as token_ledger_svc

# Normalize gamil -> gmail typo
def normalize_email(email: str) -> str:
    return email.strip().lower().replace("@gamil.com", "@gmail.com")


def main():
    if len(sys.argv) < 3:
        print("Usage: python scripts/add_tokens_for_email.py <email> <tokens>")
        sys.exit(1)
    email = normalize_email(sys.argv[1])
    try:
        amount = float(sys.argv[2])
    except ValueError:
        print("Tokens must be a number")
        sys.exit(1)
    if amount <= 0:
        print("Tokens must be positive")
        sys.exit(1)

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        if not user:
            print(f"No user found: {email}")
            sys.exit(1)
        new_remaining = token_ledger_svc.add_tokens(db, user.id, amount, "admin_add")
        db.commit()
        print(f"Added {amount} tokens for {email} (user_id={user.id}). New remaining: {new_remaining}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(0 if main() == 0 else 1)
