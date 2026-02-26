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
        row = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == user.id).first()
        if not row:
            row = models.UserTokenBalance(user_id=user.id, purchased_tokens=0.0)
            db.add(row)
            db.flush()
        prev = float(row.purchased_tokens or 0)
        row.purchased_tokens = prev + amount
        db.commit()
        print(f"Added {amount} tokens for {email} (user_id={user.id}). Balance: {prev} -> {row.purchased_tokens}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(0 if main() == 0 else 1)
