"""
Test fetching repaid lending trades from Bitfinex (POST /v2/auth/r/funding/trades/hist).
This is the same endpoint the server uses for gross profit: sum of trades between
registration date and latest.

Run with API keys from environment (do not commit real keys to repo):

  Windows (PowerShell):
    $env:API_KEY="your_key"; $env:API_SECRET="your_secret"; python scripts/test_funding_trades_fetch.py
  Linux/Mac:
    API_KEY=your_key API_SECRET=your_secret python scripts/test_funding_trades_fetch.py

Or add API_KEY and API_SECRET to .env in project root.
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

API_KEY = os.getenv("API_KEY", "").strip()
API_SECRET = os.getenv("API_SECRET", "").strip()


async def main():
    if not API_KEY or not API_SECRET:
        print("Set API_KEY and API_SECRET in .env or environment, then run again.")
        return 1

    from services.bitfinex_service import BitfinexManager

    mgr = BitfinexManager(API_KEY, API_SECRET)
    # Same window as "10 days ago" registration: from 10 days ago to now
    now = datetime.now(timezone.utc)
    start_ms = int((now - timedelta(days=10)).timestamp() * 1000)
    end_ms = int(now.timestamp() * 1000)

    print("Calling POST /v2/auth/r/funding/trades/hist (repaid lending trades, start=10d ago, limit=1000)...")
    trades, err = await mgr.funding_trades_hist(start_ms=start_ms, end_ms=end_ms, limit=1000)
    if err:
        print(f"Error: {err}")
        return 1
    if not isinstance(trades, list):
        print(f"Unexpected response type: {type(trades)}")
        return 1

    print(f"Trades returned: {len(trades)}")
    if not trades:
        print("No repaid lending trades in the last 10 days. Check the account has lending activity.")
        return 0

    # Table header
    print("\n--- Trading record (repaid funding trades) ---")
    print(f"{'#':<4} {'ID':<10} {'CURRENCY':<8} {'MTS_CREATE':<14} {'AMOUNT':<14} {'RATE':<10} {'PERIOD':<8} {'INTEREST(ccy)':<14}")
    print("-" * 90)
    for i, row in enumerate(trades[:50]):
        if isinstance(row, (list, tuple)) and len(row) >= 7:
            tid = row[0]
            currency = (row[1] or "").strip()
            mts = row[2]
            amount = float(row[4]) if row[4] is not None else 0.0
            rate = float(row[5]) if row[5] is not None else 0.0
            period = float(row[6]) if row[6] is not None else 0.0
            interest_ccy = abs(amount) * rate * (period / 365.0) if period > 0 else 0.0
            dt = datetime.fromtimestamp(mts / 1000.0, tz=timezone.utc).strftime("%Y-%m-%d %H:%M") if mts else ""
            print(f"{i+1:<4} {tid!s:<10} {currency:<8} {dt:<14} {amount:<14.4f} {rate:<10.4f} {period:<8.0f} {interest_ccy:<14.6f}")
        else:
            print(f"{i+1}. {row}")
    if len(trades) > 50:
        print(f"... and {len(trades) - 50} more trades")

    # --- Same calculation as server: per-currency interest then to USD ---
    STABLECOINS = frozenset(("USD", "USDt", "USDT", "UST", "USDC", "DAI", "TUSD", "BUSD", "FRAX"))
    by_currency = {}
    for row in trades:
        if not isinstance(row, (list, tuple)) or len(row) < 7:
            continue
        currency = (row[1] or "").strip().upper()
        if currency.startswith("F"):
            currency = currency[1:]
        amount = float(row[4]) if row[4] is not None else 0.0
        rate = float(row[5]) if row[5] is not None else 0.0
        period = float(row[6]) if row[6] is not None else 0.0
        if not currency or period <= 0:
            continue
        interest_ccy = abs(amount) * rate * (period / 365.0)
        if interest_ccy > 0:
            by_currency[currency] = by_currency.get(currency, 0.0) + interest_ccy

    need_price = [c for c in by_currency if c not in STABLECOINS]
    ticker_prices = {}
    if need_price:
        from services.bitfinex_service import _get_tickers_sync
        symbols = [f"t{c}USD" for c in need_price]
        tickers, _ = _get_tickers_sync(symbols)
        if tickers:
            for r in tickers:
                if isinstance(r, (list, tuple)) and len(r) >= 8:
                    sym = (r[0] or "").strip()
                    price = float(r[7]) if r[7] is not None else 0.0
                    if sym:
                        ticker_prices[sym] = price

    print("\n--- Calculation breakdown (formula: |AMOUNT| * RATE * (PERIOD/365 days)) ---")
    print(f"{'CURRENCY':<10} {'INTEREST(ccy)':<18} {'PRICE_USD':<12} {'INTEREST_USD':<14}")
    print("-" * 58)
    total_usd = 0.0
    for currency in sorted(by_currency.keys()):
        interest_ccy = by_currency[currency]
        if currency in STABLECOINS:
            price = 1.0
        else:
            price = ticker_prices.get(f"t{currency}USD", 0.0) or 0.0
        interest_usd = interest_ccy * price
        total_usd += interest_usd
        print(f"{currency:<10} {interest_ccy:<18.6f} {price:<12.4f} {interest_usd:<14.6f}")
    print("-" * 58)
    print(f"TOTAL GROSS USD: {total_usd:.6f}")
    print(f"  (Bitfinex fee 15%: {-total_usd * 0.15:.2f}); Net: {total_usd * 0.85:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(0 if asyncio.run(main()) == 0 else 1)
