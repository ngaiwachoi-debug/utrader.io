"""
Fetch Bitfinex ledger for user 2 and print daily gross profit for today and yesterday (UTC).
Uses same logic as _daily_10_00_fetch_and_save (no DB write).

Run from project root:
  python scripts/show_daily_gross_uid2.py [user_id]
  Default user_id=2.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta
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
    from main import (
        _get_ledger_currencies_for_user,
        _fetch_all_margin_funding_entries,
        _fetch_ticker_prices,
        _gross_and_fees_from_ledger_entries,
    )
    from services.bitfinex_service import BitfinexManager

    db = database.SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user or not getattr(user, "vault", None):
            print(f"No user or vault for user_id={user_id}")
            return 1
        keys = user.vault.get_keys()
        mgr = BitfinexManager(keys["bfx_key"], keys["bfx_secret"])
        ledger_currencies = await _get_ledger_currencies_for_user(mgr)
        if not ledger_currencies:
            ledger_currencies = None  # use default in _fetch_all_margin_funding_entries
        entries, latest_mts, fetch_err = await _fetch_all_margin_funding_entries(mgr, currencies=ledger_currencies)
        if fetch_err and not entries:
            print(f"Fetch error: {fetch_err}")
            return 1
        currencies_in_entries = {str(e[1]).strip() for e in entries if isinstance(e, (list, tuple)) and len(e) > 1 and e[1]}
        usd_prices = _fetch_ticker_prices(currencies_in_entries) if currencies_in_entries else {}

        today = datetime.utcnow().date()
        yesterday = today - timedelta(days=1)
        start_today_ms = int(datetime(today.year, today.month, today.day).timestamp() * 1000)
        end_today_ms = start_today_ms + 86400 * 1000 - 1
        start_yesterday_ms = int(datetime(yesterday.year, yesterday.month, yesterday.day).timestamp() * 1000)
        end_yesterday_ms = start_yesterday_ms + 86400 * 1000 - 1

        daily_gross_today, fees_today = _gross_and_fees_from_ledger_entries(
            entries, start_ms=start_today_ms, end_ms=end_today_ms, usd_prices=usd_prices
        )
        daily_gross_yesterday, fees_yesterday = _gross_and_fees_from_ledger_entries(
            entries, start_ms=start_yesterday_ms, end_ms=end_yesterday_ms, usd_prices=usd_prices
        )

        snap = db.query(models.UserProfitSnapshot).filter(models.UserProfitSnapshot.user_id == user_id).first()
        print(f"=== Daily gross profit (Bitfinex ledger) user_id={user_id} ===\n")
        print(f"UTC today:    {today}")
        print(f"UTC yesterday: {yesterday}\n")
        print("From Bitfinex ledger (this run):")
        print(f"  Today:    daily_gross = {daily_gross_today:.6f} USD  (fees = {fees_today:.6f})")
        print(f"  Yesterday: daily_gross = {daily_gross_yesterday:.6f} USD  (fees = {fees_yesterday:.6f})")
        if snap:
            print("\nFrom DB (user_profit_snapshot):")
            print(f"  daily_gross_profit_usd:    {getattr(snap, 'daily_gross_profit_usd', None)}")
            print(f"  last_daily_snapshot_date:  {getattr(snap, 'last_daily_snapshot_date', None)}")
            print(f"  last_deduction_processed_date: {getattr(snap, 'last_deduction_processed_date', None)}")
            print(f"  gross_profit_usd:          {getattr(snap, 'gross_profit_usd', None)}")
        else:
            print("\nNo user_profit_snapshot row for this user.")
        print(f"\nLedger entries count: {len(entries)}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
