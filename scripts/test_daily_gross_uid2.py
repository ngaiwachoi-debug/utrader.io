"""
Test daily_gross profit for user_id=2 using current logic (Option B + USD conversion).
Read-only: fetches ledgers and prints computed daily_gross for today UTC; does not write to DB.
Usage: python scripts/test_daily_gross_uid2.py [user_id]
"""
import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")


async def main():
    user_id = int(sys.argv[1]) if len(sys.argv) > 1 else 2
    import database
    import models
    from services.bitfinex_service import BitfinexManager
    from main import (
        _get_ledger_currencies_for_user,
        _fetch_all_margin_funding_entries,
        _gross_and_fees_from_ledger_entries,
        _fetch_ticker_prices,
    )

    db = database.SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user or not getattr(user, "vault", None):
            print(f"No user or vault for user_id={user_id}")
            return 1
        keys = user.vault.get_keys()
        mgr = BitfinexManager(keys["bfx_key"], keys["bfx_secret"])
        email = getattr(user, "email", None) or ""

        today = datetime.utcnow().date()
        start_today_ms = int(datetime(today.year, today.month, today.day).timestamp() * 1000)
        end_today_ms = start_today_ms + 86400 * 1000 - 1

        print(f"=== Daily gross profit test for user_id={user_id} ({email}) ===\n")
        print(f"UTC date: {today}\n")

        ledger_currencies = await _get_ledger_currencies_for_user(mgr)
        if not ledger_currencies:
            from main import LEDGER_FUNDING_CURRENCIES
            ledger_currencies = list(LEDGER_FUNDING_CURRENCIES)
            print("Option B: fallback (using full LEDGER_FUNDING_CURRENCIES)")
        else:
            print(f"Option B: currencies from credits+wallets ({len(ledger_currencies)}): {ledger_currencies}")
        print()

        entries, latest_mts, fetch_err = await _fetch_all_margin_funding_entries(mgr, currencies=ledger_currencies)
        if fetch_err:
            print(f"Fetch warning: {fetch_err}")
        print(f"Ledger entries fetched: {len(entries)}")
        if latest_mts:
            print(f"Latest entry MTS: {latest_mts}\n")

        currencies_in_entries = {
            str(e[1]).strip() for e in entries
            if isinstance(e, (list, tuple)) and len(e) > 1 and e[1]
        }
        usd_prices = _fetch_ticker_prices(currencies_in_entries) if currencies_in_entries else {}
        if usd_prices:
            print(f"USD prices used (tCCYUSD): {list(usd_prices.keys())}\n")

        daily_gross, daily_fees = _gross_and_fees_from_ledger_entries(
            entries, start_ms=start_today_ms, end_ms=end_today_ms, usd_prices=usd_prices
        )
        gross_all, fees_all = _gross_and_fees_from_ledger_entries(
            entries, start_ms=None, end_ms=None, usd_prices=usd_prices
        )

        print("Result:")
        print(f"  daily_gross_profit_usd (today): {daily_gross:.2f}")
        print(f"  daily_fees_usd (today):          {daily_fees:.2f}")
        print(f"  cumulative gross_usd (all):      {gross_all:.2f}")
        print(f"  cumulative fees_usd (all):       {fees_all:.2f}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
