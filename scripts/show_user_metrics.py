"""
One-off: show all Metric & Value for a user (user_id=2, choiwangai@gmail.com) from DB.
Uses project DATABASE_URL from .env. Run: python scripts/show_user_metrics.py
"""
import os
import sys
from pathlib import Path

# Project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.chdir(Path(__file__).resolve().parent.parent)

from dotenv import load_dotenv
load_dotenv()

from database import SessionLocal
import models

USER_ID = 2
EMAIL = "choiwangai@gmail.com"


def fmt(v):
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return v
    return str(v)


def main():
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.id == USER_ID).first()
        if not user:
            print(f"No user with id={USER_ID} (email={EMAIL})")
            return

        print("=" * 60)
        print(f"User: {user.email} (user_id={user.id})")
        print("=" * 60)

        # --- users (profile) ---
        print("\n--- users ---")
        for col in models.User.__table__.columns:
            if col.name in ("encrypted_key", "encrypted_secret", "encrypted_gemini_key"):
                continue
            val = getattr(user, col.name, None)
            print(f"  {col.name}: {fmt(val)}")

        # --- api_vault ---
        vault = db.query(models.APIVault).filter(models.APIVault.user_id == USER_ID).first()
        print("\n--- api_vault ---")
        if not vault:
            print("  (no row)")
        else:
            for col in models.APIVault.__table__.columns:
                if "encrypted" in col.name:
                    print(f"  {col.name}: <redacted>")
                else:
                    print(f"  {col.name}: {fmt(getattr(vault, col.name, None))}")

        # --- user_profit_snapshot ---
        snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == USER_ID).first()
        print("\n--- user_profit_snapshot ---")
        if not snap:
            print("  (no row)")
        else:
            for col in models.UserProfitSnapshot.__table__.columns:
                print(f"  {col.name}: {fmt(getattr(snap, col.name, None))}")

        # --- user_token_balance ---
        tok = db.query(models.UserTokenBalance).filter(models.UserTokenBalance.user_id == USER_ID).first()
        print("\n--- user_token_balance ---")
        if not tok:
            print("  (no row)")
        else:
            for col in models.UserTokenBalance.__table__.columns:
                print(f"  {col.name}: {fmt(getattr(tok, col.name, None))}")

        # --- user_usdt_credit ---
        usdt = db.query(models.UserUsdtCredit).filter(models.UserUsdtCredit.user_id == USER_ID).first()
        print("\n--- user_usdt_credit ---")
        if not usdt:
            print("  (no row)")
        else:
            for col in models.UserUsdtCredit.__table__.columns:
                print(f"  {col.name}: {fmt(getattr(usdt, col.name, None))}")

        # --- performance_logs (last 10) ---
        print("\n--- performance_logs (last 10) ---")
        try:
            logs = (
                db.query(models.PerformanceLog)
                .filter(models.PerformanceLog.user_id == USER_ID)
                .order_by(models.PerformanceLog.timestamp.desc())
                .limit(10)
                .all()
            )
            if not logs:
                print("  (no rows)")
            else:
                for row in logs:
                    waroc = getattr(row, "waroc", None)
                    total_assets = getattr(row, "total_assets", None)
                    print(f"  id={row.id} timestamp={row.timestamp} waroc={waroc} total_assets={total_assets}")
        except Exception as e:
            print(f"  (skip: {e})")
            db.rollback()

        # --- deduction_log (last 10) ---
        deductions = (
            db.query(models.DeductionLog)
            .filter(models.DeductionLog.user_id == USER_ID)
            .order_by(models.DeductionLog.timestamp_utc.desc())
            .limit(10)
            .all()
        )
        print("\n--- deduction_log (last 10) ---")
        if not deductions:
            print("  (no rows)")
        else:
            for row in deductions:
                print(
                    f"  id={row.id} timestamp_utc={row.timestamp_utc} daily_gross_profit_usd={row.daily_gross_profit_usd} "
                    f"tokens_deducted={row.tokens_deducted} tokens_remaining_after={row.tokens_remaining_after}"
                )

        # --- usdt_history (last 10) ---
        usdt_hist = (
            db.query(models.UsdtHistory)
            .filter(models.UsdtHistory.user_id == USER_ID)
            .order_by(models.UsdtHistory.created_at.desc())
            .limit(10)
            .all()
        )
        print("\n--- usdt_history (last 10) ---")
        if not usdt_hist:
            print("  (no rows)")
        else:
            for row in usdt_hist:
                print(f"  id={row.id} amount={row.amount} reason={row.reason} created_at={row.created_at}")

        # --- withdrawal_requests ---
        withdrawals = (
            db.query(models.WithdrawalRequest)
            .filter(models.WithdrawalRequest.user_id == USER_ID)
            .order_by(models.WithdrawalRequest.created_at.desc())
            .limit(10)
            .all()
        )
        print("\n--- withdrawal_requests (last 10) ---")
        if not withdrawals:
            print("  (no rows)")
        else:
            for row in withdrawals:
                print(f"  id={row.id} amount={row.amount} status={row.status} created_at={row.created_at}")

        print("\n" + "=" * 60)
    finally:
        db.close()


if __name__ == "__main__":
    main()
