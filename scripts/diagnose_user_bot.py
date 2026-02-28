"""
Diagnose why a user can or cannot run the bot. Usage: python scripts/diagnose_user_bot.py [user_id]
No auth required; reads DB only. Default user_id=2.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import SessionLocal
import models
from services import token_ledger_service as token_ledger_svc

def main():
    user_id = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            print(f"User id={user_id} not found.")
            return 1
        print(f"User id={user_id} email={getattr(user, 'email', 'N/A')}")
        print("-" * 50)

        # 1. Vault / API keys (required for worker to start)
        vault = db.query(models.APIVault).filter(models.APIVault.user_id == user_id).first()
        has_vault = vault is not None
        print(f"1. API keys (vault): {'YES' if has_vault else 'NO'}")
        if not has_vault:
            print("   -> Worker will show: 'Failure: No API keys found. Bot not started.'")

        # 2. Token balance (required: > 0)
        tokens = token_ledger_svc.get_tokens_remaining(db, user_id)
        print(f"2. tokens_remaining (user_token_balance): {tokens}")
        if tokens <= 0:
            print("   -> Worker will show: 'Failure: No tokens remaining (...). Bot not started.'")
            print("   -> POST /start-bot returns 400 INSUFFICIENT_TOKENS.")
        else:
            print("   -> Token gate OK for starting bot.")

        # 3. Bot state
        bot_status = getattr(user, "bot_status", None) or "N/A"
        bot_desired = getattr(user, "bot_desired_state", None) or "N/A"
        print(f"3. bot_status: {bot_status}")
        print(f"4. bot_desired_state: {bot_desired}")

        # 5. Plan tier (affects rebalance interval)
        plan_tier = getattr(user, "plan_tier", None) or "trial"
        print(f"5. plan_tier: {plan_tier}")

        print("-" * 50)
        if has_vault and tokens > 0:
            print("Verdict: User CAN run the bot (has keys + tokens). Start via dashboard or POST /start-bot.")
        else:
            if not has_vault:
                print("Fix: Add/save Bitfinex API keys (Settings or connect-exchange).")
            if tokens <= 0:
                print("Fix: Add tokens (purchase, admin script, or registration award if new user).")
        return 0
    finally:
        db.close()

if __name__ == "__main__":
    sys.exit(main())
