"""
Seed or refresh the top 100 referral gain (fake data). Use after migration so the Top referral gain tab has data.
Also run this to test "daily refresh" without waiting for 10:00 UTC.
Usage: python scripts/seed_referral_gain_snapshot.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from database import SessionLocal, engine
import models


def run_migration():
    path = Path(__file__).resolve().parent.parent / "migrations" / "add_referral_gain_snapshot.sql"
    sql = path.read_text()
    with engine.begin() as conn:
        for stmt in sql.split(";"):
            s = stmt.strip()
            # Skip empty or comment-only blocks
            lines = [l for l in s.splitlines() if l.strip() and not l.strip().startswith("--")]
            if not lines:
                continue
            conn.execute(text("\n".join(lines)))
    print("Migration add_referral_gain_snapshot applied (if not already).")


def _random_gmail_display(rng):
    import string
    name_len = rng.randint(4, 9)
    name_part = "".join(rng.choices(string.ascii_lowercase, k=name_len))
    suffix_len = rng.randint(3, 6)
    suffix = "".join(rng.choices(string.ascii_lowercase + string.digits, k=suffix_len))
    return f"{name_part}{suffix}@gmail.com"


def refresh_referral_gain(db):
    from datetime import date
    import random
    today = date.today()
    seed = today.year * 10000 + today.month * 100 + today.day
    rng = random.Random(seed)
    seen = set()
    rows = []
    for i in range(100):
        while True:
            user_display = _random_gmail_display(rng)
            if user_display not in seen:
                seen.add(user_display)
                break
        rows.append({
            "user_display": user_display,
            "usdt_gain_daily": round(500 + rng.uniform(0, 9500), 2),
        })
    rows.sort(key=lambda x: x["usdt_gain_daily"], reverse=True)
    db.query(models.ReferralGainSnapshot).delete()
    for r, row in enumerate(rows, start=1):
        db.add(models.ReferralGainSnapshot(
            rank=r,
            user_display=row["user_display"],
            usdt_gain_daily=row["usdt_gain_daily"],
        ))
    db.commit()
    print(f"referral_gain_snapshot refreshed: 100 rows (seed={seed}).")


def main():
    run_migration()
    db = SessionLocal()
    try:
        refresh_referral_gain(db)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
