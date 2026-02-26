"""
Update Bitfinex API keys for a user by email (writes to DB, no API server needed).
Uses same encryption as the backend. Use for dev when choiwangai shares keys.

Usage (from project root, load .env for DATABASE_URL and ENCRYPTION_KEY):
  python scripts/update_vault_by_email.py choiwangai@gmail.com <bfx_key> <bfx_secret>

Or with env vars (so keys are not in shell history):
  $env:BFTEST_KEY="..."; $env:BFTEST_SECRET="..."; python scripts/update_vault_by_email.py choiwangai@gmail.com $env:BFTEST_KEY $env:BFTEST_SECRET
"""
import os
import sys

_script_dir = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_script_dir)
if _root not in sys.path:
    sys.path.insert(0, _root)

# Load .env from project root
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(_root) / ".env")

from database import SessionLocal
import models
import security


def main():
    if len(sys.argv) < 4:
        email = (sys.argv[1] if len(sys.argv) > 1 else "").strip() or "choiwangai@gmail.com"
        key = os.getenv("BFTEST_KEY", "")
        secret = os.getenv("BFTEST_SECRET", "")
        if not key or not secret:
            print("Usage: python scripts/update_vault_by_email.py <email> <bfx_key> <bfx_secret>")
            print("Or set BFTEST_KEY and BFTEST_SECRET and run with email only.")
            sys.exit(1)
    else:
        email = sys.argv[1].strip().lower()
        key = sys.argv[2].strip()
        secret = sys.argv[3].strip()

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        if not user:
            print(f"User not found: {email}")
            sys.exit(1)
        vault = db.query(models.APIVault).filter(models.APIVault.user_id == user.id).first()
        if not vault:
            vault = models.APIVault(user_id=user.id)
            db.add(vault)
        vault.encrypted_key = security.encrypt_key(key)
        vault.encrypted_secret = security.encrypt_key(secret)
        db.commit()
        print(f"Updated vault for {email} (user_id={user.id}). Bot can use these keys.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
