"""
Clear all token deduction records from DB (and optionally reset last_deduction_processed_date).
Does NOT add tokens back; use rollback scripts per-user if you need to restore balance.
To clear the in-memory deduction log cache, restart the backend or call POST /admin/deduction/clear-cache.

  python scripts/clear_all_deduction_records.py              # delete all deduction_log rows
  python scripts/clear_all_deduction_records.py --reset     # also set last_deduction_processed_date = NULL for all users
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")


def main():
    parser = argparse.ArgumentParser(description="Clear all deduction_log rows (and optionally reset deduction date).")
    parser.add_argument("--reset", action="store_true", help="Also set last_deduction_processed_date = NULL for all users")
    args = parser.parse_args()

    import database
    import models

    db = database.SessionLocal()
    try:
        if not hasattr(models, "DeductionLog"):
            print("DeductionLog model not found. Skipping.")
            return 0

        count = db.query(models.DeductionLog).count()
        db.query(models.DeductionLog).delete(synchronize_session=False)
        db.commit()
        print(f"Deleted {count} row(s) from deduction_log.")

        if args.reset:
            updated = 0
            if hasattr(models.UserProfitSnapshot, "last_deduction_processed_date"):
                snaps = db.query(models.UserProfitSnapshot).filter(
                    models.UserProfitSnapshot.last_deduction_processed_date.isnot(None),
                ).all()
                for snap in snaps:
                    snap.last_deduction_processed_date = None
                    updated += 1
                if hasattr(models.UserProfitSnapshot, "deduction_processed"):
                    for snap in db.query(models.UserProfitSnapshot).all():
                        if getattr(snap, "deduction_processed", None) is not None:
                            snap.deduction_processed = False
                db.commit()
                print(f"Reset last_deduction_processed_date (and deduction_processed) for {updated} user(s).")
            else:
                print("UserProfitSnapshot has no last_deduction_processed_date; nothing to reset.")
        else:
            print("To allow deduction to run again for all users, run with --reset.")

        print("To clear the in-memory deduction log cache, restart the backend or POST /admin/deduction/clear-cache.")
        return 0
    except Exception as e:
        db.rollback()
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
