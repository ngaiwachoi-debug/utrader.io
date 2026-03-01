"""
Dump all user balance related tables and Bitfinex-related tables from DB.
Uses raw SQL to avoid ORM schema drift. Run: python scripts/show_balance_and_bitfinex_tables.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from database import engine
from sqlalchemy import text


def dump_table(conn, name, order_col=None):
    try:
        q = f"SELECT * FROM {name}"
        if order_col:
            q += f" ORDER BY {order_col}"
        r = conn.execute(text(q))
        rows = r.fetchall()
        cols = list(r.keys())
        return cols, rows
    except Exception as e:
        return None, str(e)


def main():
    with engine.connect() as conn:
        # ---- User balance related ----
        print("=" * 80)
        print("USER BALANCE RELATED TABLES")
        print("=" * 80)

        for table, order in [
            ("user_token_balance", "user_id"),
            ("user_usdt_credit", "user_id"),
            ("user_profit_snapshot", "user_id"),
            ("usdt_history", "id"),
            ("deduction_log", "timestamp_utc DESC"),
            ("withdrawal_requests", "created_at DESC"),
            ("referral_rewards", "id"),
        ]:
            print(f"\n--- {table} ---")
            cols, data = dump_table(conn, table, order)
            if cols is None:
                print(f"  Error: {data}")
                conn.rollback()
                continue
            print("  " + " | ".join(cols))
            print("  " + "-" * 70)
            for row in data[:30]:  # cap at 30 rows per table
                print("  " + " | ".join(str(x) for x in row))
            if len(data) > 30:
                print(f"  ... and {len(data) - 30} more rows")
            print(f"  Total rows: {len(data)}")

        # token_ledger if exists
        print("\n--- token_ledger ---")
        cols, data = dump_table(conn, "token_ledger", "id DESC")
        if cols is None:
            print(f"  (table missing or error: {data})")
            conn.rollback()
        else:
            print("  " + " | ".join(cols))
            print("  " + "-" * 70)
            for row in data[:30]:
                print("  " + " | ".join(str(x) for x in row))
            if len(data) > 30:
                print(f"  ... and {len(data) - 30} more rows")
            print(f"  Total rows: {len(data)}")

        # ---- Bitfinex calling / API related ----
        print("\n" + "=" * 80)
        print("BITFINEX-RELATED TABLES (api_vault = keys + last test result; trial_history = trial usage)")
        print("=" * 80)

        print("\n--- api_vault (encrypted columns redacted) ---")
        try:
            r = conn.execute(text(
                "SELECT user_id, created_at, last_tested_at, last_test_balance, keys_updated_at FROM api_vault ORDER BY user_id"
            ))
            rows = r.fetchall()
            cols = list(r.keys())
            print("  " + " | ".join(cols))
            print("  " + "-" * 70)
            for row in rows:
                print("  " + " | ".join(str(x) for x in row))
            print(f"  Total rows: {len(rows)}")
        except Exception as e:
            print(f"  Error: {e}")

        print("\n--- trial_history (Bitfinex accounts that used free trial) ---")
        cols, data = dump_table(conn, "trial_history", None)
        if cols is None:
            print(f"  Error: {data}")
        else:
            print("  " + " | ".join(cols))
            print("  " + "-" * 70)
            for row in data:
                print("  " + " | ".join(str(x) for x in row))
            print(f"  Total rows: {len(data)}")

        print("\n" + "=" * 80)


if __name__ == "__main__":
    main()
