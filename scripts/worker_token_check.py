"""
Simulate exactly what the worker reads for token gate: same DB, same service.
Run from project root. Usage: python scripts/worker_token_check.py [user_id]
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_env_path = Path(__file__).resolve().parent.parent / ".env"
try:
    from dotenv import load_dotenv
    load_dotenv(dotenv_path=_env_path)
except ImportError:
    pass

def main():
    user_id = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    from database import SessionLocal
    import models
    from services import token_ledger_service as token_ledger_svc

    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        print(f"User {user_id}: exists={user is not None}")
        if not user:
            return 1
        print(f"  vault (API keys): {getattr(user, 'vault', None) is not None}")
        if hasattr(user, "vault") and user.vault:
            print(f"  vault id: {user.vault.id if hasattr(user.vault, 'id') else 'N/A'}")

        # Same as worker: token_ledger_svc.get_tokens_remaining
        tokens = token_ledger_svc.get_tokens_remaining(db, user_id)
        print(f"  token_ledger_svc.get_tokens_remaining(db, {user_id}) = {tokens}")

        # Raw table check
        from sqlalchemy import text
        r = db.execute(text("SELECT user_id, tokens_remaining, purchased_tokens FROM user_token_balance WHERE user_id = :uid"), {"uid": user_id}).fetchone()
        if r:
            print(f"  user_token_balance row: user_id={r[0]} tokens_remaining={r[1]} purchased_tokens={r[2]}")
        else:
            print("  user_token_balance: NO ROW (worker would get 0)")
        print()
        if tokens <= 0:
            print("-> Worker would REFUSE to start: 'No tokens remaining. Bot not started.'")
        else:
            print("-> Worker would PASS token gate and start engine.")
        return 0
    finally:
        db.close()

if __name__ == "__main__":
    sys.exit(main())
