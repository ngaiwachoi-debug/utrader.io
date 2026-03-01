"""
Ensure choiwangai@gmail.com exists with Bitfinex API keys in vault and enough tokens to run the bot.
Uses BIFINEX_API_KEY and BIFINEX_API_SECRET from environment (do not commit keys to repo).
Works with legacy user_token_balance (tokens_remaining) or ledger schema (total_tokens_added/total_tokens_deducted).

Run from project root:
  set BIFINEX_API_KEY=your_key
  set BIFINEX_API_SECRET=your_secret
  python scripts/setup_choiwangai_for_bot_test.py
"""
import os
import sys
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from database import SessionLocal
import models
import security

EMAIL = "choiwangai@gmail.com"
MIN_TOKENS = 100  # enough to run bot (worker requires >= 1)


def main():
    key = os.getenv("BIFINEX_API_KEY", "").strip()
    secret = os.getenv("BIFINEX_API_SECRET", "").strip()
    if not key or not secret:
        print("Set BIFINEX_API_KEY and BIFINEX_API_SECRET in the environment.")
        return 1

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == EMAIL).first()
        if not user:
            user = models.User(
                email=EMAIL,
                plan_tier="trial",
                rebalance_interval=30,
            )
            user.referral_code = f"ref-{abs(hash(EMAIL)) % 10_000_000}"
            db.add(user)
            db.commit()
            db.refresh(user)
            print(f"Created user {EMAIL} (id={user.id})")
        else:
            print(f"User {EMAIL} exists (id={user.id})")

        vault = db.query(models.APIVault).filter(models.APIVault.user_id == user.id).first()
        if not vault:
            vault = models.APIVault(
                user_id=user.id,
                encrypted_key=security.encrypt_key(key),
                encrypted_secret=security.encrypt_key(secret),
            )
            db.add(vault)
            db.commit()
            db.refresh(vault)
            print("Created vault with Bitfinex keys.")
        else:
            vault.encrypted_key = security.encrypt_key(key)
            vault.encrypted_secret = security.encrypt_key(secret)
            vault.keys_updated_at = datetime.utcnow()
            db.commit()
            print("Updated vault with Bitfinex keys.")

        # Ensure token balance so Start Bot succeeds (worker needs >= 1)
        from services import token_ledger_service as token_ledger_svc
        remaining = token_ledger_svc.get_tokens_remaining(db, user.id)
        if remaining < MIN_TOKENS:
            token_ledger_svc.add_tokens(db, user.id, float(MIN_TOKENS), "admin_add")
            db.commit()
            print(f"Added tokens to at least {MIN_TOKENS} (was {remaining}).")
        else:
            print(f"Token balance OK: {remaining}")

        # Ensure profit snapshot row exists (user_status may need it)
        snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user.id).first()
        if not snap:
            db.add(models.UserProfitSnapshot(user_id=user.id, gross_profit_usd=0.0, net_profit_usd=0.0))
            db.commit()
            print("Created user_profit_snapshot row.")

        print(f"Ready: {EMAIL} (user_id={user.id}) for bot test.")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
