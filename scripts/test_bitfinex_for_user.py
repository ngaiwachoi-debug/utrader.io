"""
Test Bitfinex API response for a user (e.g. choiwangai@gmail.com).
Uses stored API keys from DB, calls Bitfinex wallets + funding_credits,
and prints totals and lent amounts so Portfolio Allocation can be verified.

Run from project root:
  python scripts/test_bitfinex_for_user.py
  python scripts/test_bitfinex_for_user.py choiwangai@gmail.com
"""
import asyncio
import sys
from pathlib import Path

# project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import SessionLocal
import models
from services.bitfinex_service import BitfinexManager
from services.bitfinex_service import _get_tickers_sync


def _total_lent_usd(lent_per_currency: dict) -> float:
    """Convert lent_per_currency to total USD; non-USD need ticker price."""
    if not lent_per_currency:
        return 0.0
    need_price = [c for c in lent_per_currency if c not in ("USD", "USDt", "USDT", "UST")]
    prices = {}
    if need_price:
        symbols = [f"t{c}USD" for c in need_price]
        tickers, _ = _get_tickers_sync(symbols)
        if tickers:
            for row in tickers:
                try:
                    if isinstance(row, (list, tuple)) and len(row) >= 8:
                        sym = (row[0] or "").strip()
                        if sym:
                            prices[sym] = float(row[7]) if row[7] is not None else 0.0
                except (TypeError, ValueError, IndexError):
                    pass
    total = 0.0
    for currency, amount in lent_per_currency.items():
        if currency in ("USD", "USDt", "USDT", "UST"):
            total += amount
        else:
            total += amount * prices.get(f"t{currency}USD", 0.0)
    return total


def _aggregate_lent(credits_data) -> dict:
    result = {}
    if not isinstance(credits_data, list):
        return result
    for row in credits_data:
        try:
            if isinstance(row, (list, tuple)) and len(row) > 5:
                symbol = (row[1] or "").strip().upper()
                if symbol.startswith("F"):
                    symbol = symbol[1:]
                amount = float(row[5]) if row[5] is not None else 0.0
                if symbol:
                    result[symbol] = result.get(symbol, 0.0) + amount
        except (TypeError, ValueError, IndexError):
            continue
    return result


async def main():
    email = (sys.argv[1] if len(sys.argv) > 1 else "choiwangai@gmail.com").strip()
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.email == email).first()
        if not user:
            print(f"User not found: {email}")
            return
        vault = db.query(models.APIVault).filter(models.APIVault.user_id == user.id).first()
        if not vault or not vault.encrypted_key or not vault.encrypted_secret:
            print(f"No API keys for {email}")
            return
        keys = vault.get_keys()
        mgr = BitfinexManager(keys["bfx_key"], keys["bfx_secret"])
        print(f"Bitfinex API test for {email} (user_id={user.id})")
        print("-" * 50)
        summary = await mgr.compute_usd_balances()
        credits, err = await mgr.funding_credits()
        if err:
            print(f"Funding credits error: {err}")
        lent_per_currency = _aggregate_lent(credits) if credits else {}
        total_lent_usd = round(_total_lent_usd(lent_per_currency), 2)
        total_usd_all = summary.get("total_usd_all") or 0.0
        print(f"total_usd_all (wallet): {total_usd_all}")
        print(f"lent_per_currency:      {lent_per_currency}")
        print(f"total_lent_usd:         {total_lent_usd}")
        print(f"pending (total - lent): {total_usd_all - total_lent_usd}")
        print("-" * 50)
        print("Portfolio Allocation should show:")
        print(f"  Actively Earning:   ${total_lent_usd:,.2f}")
        print(f"  Pending Deployment: ${total_usd_all - total_lent_usd:,.2f}")
        print(f"  Idle Funds:         $0.00")
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(main())
