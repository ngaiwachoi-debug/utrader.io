import os
from pathlib import Path
from dotenv import load_dotenv

_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=_env_path)

from database import SessionLocal
import models

def main():
    db = SessionLocal()
    print("DB: connected via DATABASE_URL")
    users = db.query(models.User).all()
    for u in users:
        print(f"User {u.id}: {u.email} - Has vault: {bool(u.vault)}")

    vaults = db.query(models.APIVault).all()
    print(f"Total Vaults: {len(vaults)}")
    for v in vaults:
        print(f"Vault for user {v.user_id}")

if __name__ == "__main__":
    main()
