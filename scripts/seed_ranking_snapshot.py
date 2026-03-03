"""
Seed or refresh the top 100 ranking (fake data). Use after migration so the Ranking page shows data.
Also run this to test "daily refresh" without waiting for 10:00 UTC.
Usage: python scripts/seed_ranking_snapshot.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from database import SessionLocal, engine
import models


def run_migration():
    path = Path(__file__).resolve().parent.parent / "migrations" / "add_ranking_snapshot.sql"
    sql = path.read_text()
    for stmt in sql.split(";"):
        s = stmt.strip()
        if s and not s.startswith("--"):
            with engine.connect() as c:
                c.execute(text(s))
                c.commit()
    print("Migration add_ranking_snapshot applied (if not already).")


def _random_gmail_display(rng):
    import string
    name_len = rng.randint(4, 9)
    name_part = "".join(rng.choices(string.ascii_lowercase, k=name_len))
    suffix_len = rng.randint(3, 6)
    suffix = "".join(rng.choices(string.ascii_lowercase + string.digits, k=suffix_len))
    return f"{name_part}{suffix}@gmail.com"


def refresh_ranking(db):
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
            "yield_pct": round(15 + rng.uniform(0, 17), 2),
            "lent_usd": round(1000 + rng.uniform(0, 99000), 2),
        })
    rows.sort(key=lambda x: x["yield_pct"], reverse=True)
    db.query(models.RankingSnapshot).delete()
    for r, row in enumerate(rows, start=1):
        db.add(models.RankingSnapshot(
            rank=r,
            user_display=row["user_display"],
            yield_pct=row["yield_pct"],
            lent_usd=row["lent_usd"],
        ))
    db.commit()
    print(f"ranking_snapshot refreshed: 100 rows (seed={seed}).")


def main():
    run_migration()
    db = SessionLocal()
    try:
        refresh_ranking(db)
    finally:
        db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
