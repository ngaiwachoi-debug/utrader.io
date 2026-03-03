"""
Stateless one-shot lending cycle for scalable workers (1000+ users).

Use this from a task queue: each job runs ONE cycle for ONE user, then exits.
The queue/Dispatcher schedules the next run after rebalance_interval minutes.
No infinite loops, no asyncio.gather of long-lived run_loop() tasks.

Uses a single nonce stream for the whole cycle (initial wallet fetch + all engines)
to avoid Bitfinex 10114 "nonce: small".

Usage:
    success, log_lines = await run_one_lending_cycle(user_id, api_key, api_secret, gemini_key, redis_pool=None)
"""

import asyncio
import hashlib
import hmac
import json
import threading
import time
from datetime import datetime

import aiohttp
from bot_engine import WallStreet_Omni_FullEngine


# Minimum USD-equivalent balance to run the engine (matches V33 threshold).
MIN_USD_THRESHOLD = 200.0

REST_URL = "https://api.bitfinex.com/v2"


async def _one_bfx_request(
    path: str,
    body: dict,
    api_key: str,
    api_secret: str,
    shared_nonce_ref: tuple,
) -> list | dict | None:
    """Perform one signed Bitfinex request using the shared nonce. Returns JSON or None on error."""
    lst, lock = shared_nonce_ref
    with lock:
        lst[0] += 1
        nonce = str(lst[0])
    payload = json.dumps(body) if body else "{}"
    signature = f"/api/v2{path}{nonce}{payload}"
    sig_hex = hmac.new(api_secret.encode(), signature.encode(), hashlib.sha384).hexdigest()
    headers = {
        "bfx-nonce": nonce,
        "bfx-apikey": api_key,
        "bfx-signature": sig_hex,
        "Content-Type": "application/json",
    }
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{REST_URL}{path}", headers=headers, json=body, timeout=10) as resp:
                if resp.status != 200:
                    return None
                out = await resp.json()
                if isinstance(out, list) and len(out) > 0 and out[0] == "error":
                    return None
                return out
    except Exception:
        return None


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
        # Single nonce stream + serialized requests for entire cycle to avoid Bitfinex 10114 "nonce: small"
        shared_nonce = [int(time.time() * 1000000)]
        nonce_lock = threading.Lock()
        shared_nonce_ref = (shared_nonce, nonce_lock)
        bfx_request_lock = asyncio.Lock()

        # One-time wallet fetch using same nonce as engines (hold lock so engines start after)
        async with bfx_request_lock:
            wallets = await _one_bfx_request("/auth/r/wallets", {}, api_key, api_secret, shared_nonce_ref)
        if not wallets or (isinstance(wallets, list) and len(wallets) > 0 and wallets[0] == "error"):
            _log("No wallets response or API error; skipping cycle.")
            return False, log

        def _balance(w) -> float:
            try:
                b = float(w[2]) if len(w) > 2 and w[2] is not None else 0.0
                if b > 0:
                    return b
                return float(w[4]) if len(w) > 4 and w[4] is not None else 0.0
            except (TypeError, ValueError, IndexError):
                return 0.0

        funding = [
            (w[1], _balance(w))
            for w in wallets
            if isinstance(w, (list, tuple)) and len(w) >= 3 and w[0] == "funding" and _balance(w) > 0
        ]
        if not funding:
            _log("No funding balance (w[2]/w[4]); skipping cycle.")
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
                shared_nonce_ref=shared_nonce_ref,
                bfx_request_lock=bfx_request_lock,
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
