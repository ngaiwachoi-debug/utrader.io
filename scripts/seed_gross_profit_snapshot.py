"""
One-off: upsert user_profit_snapshot for a user so Gross Profit shows the persisted value
(e.g. when cache/API returned 0 but the correct value is known).
Uses raw SQL so it works even if the DB is missing optional columns (e.g. daily_gross_profit_usd).
Usage: python scripts/seed_gross_profit_snapshot.py [email] [gross_profit_usd]
  email defaults to choiwangai@gmail.com, gross_profit_usd defaults to 72.20
Run from project root.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import SessionLocal
from sqlalchemy import text

EMAIL = sys.argv[1] if len(sys.argv) > 1 else "choiwangai@gmail.com"
GROSS = float(sys.argv[2]) if len(sys.argv) > 2 else 72.20
FEE_PCT = 0.15


def main():
    db = SessionLocal()
    try:
        user = db.execute(text("SELECT id FROM users WHERE email = :email"), {"email": EMAIL}).fetchone()
        if not user:
            print(f"User not found: {EMAIL}")
            return 1
        user_id = user[0]
        fee = round(GROSS * FEE_PCT, 2)
        net = round(GROSS * (1 - FEE_PCT), 2)
        existing = db.execute(
            text("SELECT user_id FROM user_profit_snapshot WHERE user_id = :uid"),
            {"uid": user_id},
        ).fetchone()
        if existing:
            db.execute(
                text(
                    "UPDATE user_profit_snapshot SET gross_profit_usd = :g, bitfinex_fee_usd = :f, net_profit_usd = :n, updated_at = NOW() WHERE user_id = :uid"
                ),
                {"g": GROSS, "f": fee, "n": net, "uid": user_id},
            )
            print(f"Updated user_profit_snapshot for {EMAIL} (user_id={user_id}): gross_profit_usd={GROSS}")
        else:
            db.execute(
                text(
                    "INSERT INTO user_profit_snapshot (user_id, gross_profit_usd, bitfinex_fee_usd, net_profit_usd) VALUES (:uid, :g, :f, :n)"
                ),
                {"uid": user_id, "g": GROSS, "f": fee, "n": net},
            )
            print(f"Inserted user_profit_snapshot for {EMAIL} (user_id={user_id}): gross_profit_usd={GROSS}")
        db.commit()
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
