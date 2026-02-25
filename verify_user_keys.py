"""
Self-verify: Check that User ID 1 has encrypted_api_key and encrypted_api_secret populated in the database.
Uses api_vault table (columns encrypted_key, encrypted_secret).
"""
import sys
from database import SessionLocal
import models

def main():
    db = SessionLocal()
    try:
        vault = db.query(models.APIVault).filter(models.APIVault.user_id == 1).first()
        if not vault:
            print("FAIL: No api_vault row for user_id=1.")
            sys.exit(1)
        has_key = bool(vault.encrypted_key and vault.encrypted_key.strip())
        has_secret = bool(vault.encrypted_secret and vault.encrypted_secret.strip())
        if has_key and has_secret:
            print("OK: User ID 1 has encrypted_api_key and encrypted_api_secret populated.")
            sys.exit(0)
        print(f"FAIL: User ID 1 vault: encrypted_key populated={has_key}, encrypted_secret populated={has_secret}.")
        sys.exit(1)
    finally:
        db.close()

if __name__ == "__main__":
    main()
