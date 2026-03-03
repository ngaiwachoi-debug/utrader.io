"""
Check USD and USDT (w[4] = AVAILABLE_BALANCE) for user id 2 from Bitfinex /auth/r/wallets.
Compares with funding offers to compute bot-style "available" (balance - in_offers) and
verifies whether the bot would create orders for each currency.
Run from project root: python scripts/check_wallet_available_user2.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from database import SessionLocal
import models
from services.bitfinex_service import BitfinexManager

MIN_ORDER_USD = 150.0  # bot_engine.MIN_ORDER_USD


def norm_currency(s: str) -> str:
    if not s:
        return ""
    c = (s or "").strip().upper()
    if c in ("USDT", "UST"):
        return "UST"
    return c


def aggregate_offers_per_currency(offers_data: list) -> dict:
    """Same as bot_engine._aggregate_offers_per_currency: symbol at 1, amount at 4."""
    result = {}
    for row in offers_data or []:
        try:
            if not isinstance(row, (list, tuple)) or len(row) <= 4:
                continue
            sym = (row[1] or "").strip().upper()
            if sym.startswith("F"):
                sym = sym[1:]
            curr = norm_currency(sym)
            amount = float(row[4]) if row[4] is not None else 0.0
            if curr:
                result[curr] = result.get(curr, 0.0) + amount
        except (TypeError, ValueError, IndexError):
            continue
    return result


async def main():
    user_id = 2
    db = SessionLocal()
    try:
        user = db.query(models.User).filter(models.User.id == user_id).first()
        if not user:
            print(f"User id={user_id} not found.")
            return 1
        vault = db.query(models.APIVault).filter(models.APIVault.user_id == user_id).first()
        if not vault or not vault.encrypted_key or not vault.encrypted_secret:
            print(f"No API keys for user id={user_id}")
            return 1
        keys = vault.get_keys()
        mgr = BitfinexManager(keys["bfx_key"], keys["bfx_secret"])

        # 1) Wallets (same API as bot: /auth/r/wallets)
        wallets, err = await mgr.wallets()
        if err:
            print(f"Bitfinex wallets error: {err}")
            return 1
        if not wallets or not isinstance(wallets, list):
            print("No wallets response.")
            return 1

        # 2) Funding offers (same as bot: used for balance - offers when w[4] is null/0)
        offers, err_offers = await mgr.funding_offers()
        if err_offers:
            print(f"Bitfinex funding_offers error: {err_offers}")
        offers_list = offers if isinstance(offers, list) and offers and offers[0] != "error" else []
        offers_per_currency = aggregate_offers_per_currency(offers_list)

        # Bitfinex wallet: [0]=TYPE, [1]=CURRENCY, [2]=BALANCE, [3]=UNSETTLED_INTEREST, [4]=AVAILABLE_BALANCE
        print(f"User id={user_id} ({getattr(user, 'email', 'N/A')}) - Bitfinex w[4] check (USD & USDT)")
        print("=" * 80)
        print(f"{'CURRENCY':<10} {'BALANCE w[2]':<18} {'AVAILABLE w[4]':<18} {'In offers':<14} {'Bot available':<16} Same value?  Create orders?")
        print("-" * 80)

        for label, wallet_currency, offer_key in [("USD", "USD", "USD"), ("USDT", None, "UST")]:
            if wallet_currency:
                row = next((w for w in wallets if isinstance(w, (list, tuple)) and w[0] == "funding" and w[1] == wallet_currency), None)
            else:
                row = next((w for w in wallets if isinstance(w, (list, tuple)) and w[0] == "funding" and (w[1] or "").upper() in ("USDT", "UST")), None)
            if not row:
                print(f"{label:<10} (no funding wallet)")
                continue
            balance = float(row[2]) if len(row) > 2 and row[2] is not None else 0.0
            raw_w4 = row[4] if len(row) > 4 else None
            try:
                available_w4 = float(raw_w4) if raw_w4 is not None else None
            except (TypeError, ValueError):
                available_w4 = None
            in_offers = offers_per_currency.get(offer_key, 0.0)
            # Bot logic: use w[4] if not null and >= MIN_ORDER_AMT, else available = balance - in_offers
            if available_w4 is not None and available_w4 >= MIN_ORDER_USD:
                bot_available = available_w4
                same_value = "yes (uses w[4])"
            else:
                bot_available = max(0.0, balance - in_offers)
                same_value = "yes (uses bal-offers)" if (available_w4 is None or available_w4 < MIN_ORDER_USD) else "no (w[4]<MIN, bot uses bal-offers)"
            create_orders = "YES" if bot_available >= MIN_ORDER_USD else "NO"
            w4_str = f"{available_w4:,.4f}" if available_w4 is not None else str(repr(raw_w4))
            print(f"{label:<10} {balance:>16,.4f}   {w4_str:<18} {in_offers:>12,.4f}   {bot_available:>14,.4f}   {same_value:<14} {create_orders}")

        print("-" * 80)
        print("\nRaw funding wallets (all):")
        for w in wallets:
            if not isinstance(w, (list, tuple)) or w[0] != "funding":
                continue
            curr = w[1] if len(w) > 1 else ""
            bal = float(w[2]) if len(w) > 2 and w[2] is not None else None
            avail_raw = w[4] if len(w) > 4 else "N/A"
            print(f"  {curr:<8} balance={bal}  w[4]={repr(avail_raw)}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
