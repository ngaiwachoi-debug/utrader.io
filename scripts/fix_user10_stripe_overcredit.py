"""
One-off: Fix user 10 (or any user) over-credited by Stripe webhook double/quad delivery.

User 10 received 320000 tokens for 2 Whales monthly purchases (should be 80000).
This script deducts the over-credited amount so balance = 40000 * number_of_purchases.

Usage:
  python scripts/fix_user10_stripe_overcredit.py              # user_id=10, 2 purchases -> set to 80000
  python scripts/fix_user10_stripe_overcredit.py --user 10 --purchases 2
  python scripts/fix_user10_stripe_overcredit.py --user 10 --target 40000   # set balance to 40000

Run from project root. Requires DATABASE_URL. Use --dry-run to print what would be done.
"""
import argparse
import os
import sys

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"))
except ImportError:
    pass

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("DATABASE_URL not set")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--user", type=int, default=10)
    parser.add_argument("--purchases", type=int, default=2, help="Number of Whales monthly purchases (40k each)")
    parser.add_argument("--target", type=int, default=None, help="Set balance to this instead of 40000 * purchases")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    target_balance = args.target if args.target is not None else (40000 * args.purchases)
    engine = create_engine(DATABASE_URL)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    db = SessionLocal()

    try:
        r = db.execute(text("SELECT tokens_remaining FROM user_token_balance WHERE user_id = :uid"), {"uid": args.user}).fetchone()
        if not r:
            print(f"User {args.user} has no token balance row")
            sys.exit(1)
        current = float(r[0] or 0)
        if current < target_balance:
            print(f"Current {current} < target {target_balance}; not increasing balance (use admin add if needed)")
            sys.exit(0)
        to_deduct = current - target_balance
        if to_deduct <= 0:
            print(f"User {args.user} balance {current} already <= target {target_balance}")
            sys.exit(0)
        print(f"User {args.user}: current={current}, target={target_balance}, will deduct {to_deduct}")
        if args.dry_run:
            print("(dry-run, no changes)")
            sys.exit(0)
        db.execute(
            text("""
                UPDATE user_token_balance
                SET tokens_remaining = tokens_remaining - :deduct,
                    updated_at = NOW()
                WHERE user_id = :uid
            """),
            {"uid": args.user, "deduct": to_deduct},
        )
        try:
            db.execute(
                text("UPDATE user_token_balance SET total_tokens_deducted = total_tokens_deducted + :deduct WHERE user_id = :uid"),
                {"uid": args.user, "deduct": to_deduct},
            )
        except Exception:
            pass
        try:
            db.execute(
                text("""
                    INSERT INTO token_ledger (user_id, activity_type, amount, reason, metadata)
                    VALUES (:uid, 'deduct', :amt, 'admin_adjustment', CAST(:meta AS jsonb))
                """),
                {"uid": args.user, "amt": -to_deduct, "meta": '{"note": "Stripe webhook over-credit correction"}'},
            )
        except Exception:
            pass
        db.commit()
        r2 = db.execute(text("SELECT tokens_remaining FROM user_token_balance WHERE user_id = :uid"), {"uid": args.user}).fetchone()
        print(f"Done. New balance: {r2[0]}")
    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        sys.exit(1)
    finally:
        db.close()


if __name__ == "__main__":
    main()
