"""
Stateless one-shot lending cycle for scalable workers (1000+ users).

Use this from a task queue: each job runs ONE cycle for ONE user, then exits.
The queue/Dispatcher schedules the next run after rebalance_interval minutes.
No infinite loops, no asyncio.gather of long-lived run_loop() tasks.

Usage:
    success, log_lines = await run_one_lending_cycle(user_id, api_key, api_secret, gemini_key, redis_pool=None)
"""

import asyncio
from datetime import datetime

from bot_engine import WallStreet_Omni_FullEngine


# Minimum USD-equivalent balance to run the engine (matches V33 threshold).
MIN_USD_THRESHOLD = 200.0


async def run_one_lending_cycle(
    user_id: int,
    api_key: str,
    api_secret: str,
    gemini_key: str,
    redis_pool=None,
) -> tuple[bool, list[str]]:
    """
    Runs a single lending cycle for the user: scan wallets, for each qualified
    asset run snapshot + portfolio check + cancel stuck + deploy matrix, then return.
    No WebSocket, no infinite loop. Safe for 1000+ users when invoked per job.
    """
    log: list[str] = []
    now = datetime.now().strftime("%H:%M:%S")

    def _log(msg: str) -> None:
        log.append(f"[{now}] {msg}")
        print(f"[{now}] [User {user_id}] {msg}")

    try:
        # One-time wallet fetch (shared nonce/session via a minimal manager call)
        from bot_engine import PortfolioManager
        manager = PortfolioManager(
            user_id=user_id,
            api_key=api_key,
            api_secret=api_secret,
            gemini_key=gemini_key or "",
            redis_pool=redis_pool,
        )
        wallets = await manager._api_request("/auth/r/wallets", {})
        if not wallets:
            _log("No wallets response; skipping cycle.")
            return False, log

        funding = [
            (w[1], float(w[2]))
            for w in wallets
            if w[0] == "funding" and float(w[2]) > 0
        ]
        if not funding:
            _log("No funding balance; skipping cycle.")
            return True, log

        # Spot prices: default 1.0 for USD/UST; others we could fetch (optional).
        spot_prices: dict[str, float] = {"USD": 1.0, "UST": 1.0, "USDT": 1.0}
        for currency, _ in funding:
            if currency not in spot_prices:
                spot_prices[currency] = 1.0  # Conservative; add REST ticker fetch if needed.

        ran = 0
        for currency, balance in funding:
            usd_val = balance * spot_prices.get(currency, 1.0)
            if usd_val < MIN_USD_THRESHOLD:
                continue
            engine = WallStreet_Omni_FullEngine(
                user_id=user_id,
                api_key=api_key,
                api_secret=api_secret,
                gemini_key=gemini_key or "",
                currency=currency,
                spot_price=spot_prices.get(currency, 1.0),
                redis_pool=redis_pool,
            )
            await engine.fetch_instant_snapshot()
            await engine.check_portfolio_status()
            await engine.cancel_stuck_senior_orders()
            await engine.deploy_matrix(full_rebuild=True)
            ran += 1

        if ran:
            _log(f"Cycle complete for {ran} asset(s).")
        else:
            _log("No assets above threshold; cycle skipped.")
        return True, log
    except asyncio.CancelledError:
        _log("Cycle cancelled.")
        return False, log
    except Exception as e:
        _log(f"Cycle error: {e}")
        return False, log
