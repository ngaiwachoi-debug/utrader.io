"""
bot_engine.py

Core isolated algorithmic lending engine for Bitfinex.
Enhanced with Redis Heartbeat broadcasting for the Bifinex Bot Dashboard.
Multi-tenant ready: all variables are isolated per instance.
"""

import asyncio
import aiohttp
import math
import os
import threading
import websockets
import json
import time
import hmac
import hashlib
import numpy as np
from pathlib import Path
from datetime import datetime
from google import genai

from services.shared_oracle import get_oracle_snapshot
from services.ai_injector import AI_ContextInjector
from services.bitfinex_nonce import get_next_nonce

# Institutional baselines (lag = minutes until lending rate typically spikes after BTC volume surge)
IQM_BASELINES_PATH = Path(__file__).resolve().parent / "data" / "iqm_baselines.json"
DEFAULT_LAG_MINUTES_COMPOSITE = 34

# Tier rebalance intervals (minutes). Must match worker.PLAN_CONFIG when using ARQ.
PLAN_CONFIG = {
    "trial": {"sleep_minutes": 40},
    "free": {"sleep_minutes": 40},
    "pro": {"sleep_minutes": 20},
    "ai_ultra": {"sleep_minutes": 10},
    "whales": {"sleep_minutes": 3},
}

MAX_ORDER_SLOTS = 100
SHADOW_DRIP_FRACTION = 0.20  # Submit 20% of ladder immediately
SHATTER_CHUNK_USD_HIGH_VOL = 1000.0   # When v_sigma > 2.0
SHATTER_CHUNK_USD_NORMAL = 3000.0
MIN_ORDER_USD = 150.0
ORACLE_STALE_SEC = 120


def _strategy_b_gate_enabled() -> bool:
    """When True, only place when current FRR >= 24h rolling median. Set STRATEGY_B_GATE_ENABLED=0 to disable."""
    v = (os.environ.get("STRATEGY_B_GATE_ENABLED", "1") or "").strip().lower()
    return v in ("1", "true", "yes")


class WallStreet_Omni_FullEngine:
    """
    Autonomous Crypto Lending Engine. 
    Manages funding book deployments and broadcasts live stats to Redis.
    """
    def __init__(self, user_id: int, api_key: str, api_secret: str, gemini_key: str, currency: str, spot_price: float, redis_pool=None, log_lines: list | None = None, shared_nonce_ref=None, bfx_request_lock=None):
        self.user_id = user_id
        self.api_key = api_key
        self.api_secret = api_secret
        self.gemini_key = gemini_key
        self.redis_pool = redis_pool # 🟢 Injected Redis pool for Dashboard
        self.log_lines = log_lines  # optional list to capture lines for Whales terminal
        # shared_nonce_ref: (mutable_list, threading.Lock) so multiple engines (USD/UST) share one nonce per API key
        self._shared_nonce_ref = shared_nonce_ref
        # bfx_request_lock: asyncio.Lock to serialize Bitfinex API requests per key (avoid 10114 nonce: small)
        self._bfx_request_lock = bfx_request_lock
        self._nonce = int(time.time() * 1000000)
        self.wallet_currency = currency
        self.symbol = f"f{currency}"
        self.spot_price = spot_price 
        
        # Bitfinex enforces "minimum is 150.0 dollar or equivalent". For stablecoins
        # (UST/USDT) that can trade at a slight discount to USD, use a higher base amount
        # to avoid "incorrect amount" rejections. USD is exactly 1:1 so less margin needed.
        _min_base = 152.0 if currency.upper() in ("UST", "USDT", "USDt") else 150.50
        self.MIN_ORDER_AMT = _min_base / self.spot_price if self.spot_price > 0 else 0
        self.SWEEP_AMT = 500.0 / self.spot_price if self.spot_price > 0 else 0
        
        # Dashboard State Tracking
        self.waroc = 0.0
        self.total_loaned = 0.0
        self.total_balance = 0.0
        self._last_idle_log_time = 0.0  # throttle "idle" logs to every 5 min

        # AI Initialization
        try:
            self.ai_client = genai.Client(api_key=self.gemini_key)
            self.ai_enabled = True
            self.last_ai_request = 0 
        except Exception as e:
            print(f"[{self._now()}] [User {self.user_id}] AI Init Failed: {e}. Running Offline.")
            self.ai_enabled = False

        self.rest_url = "https://api.bitfinex.com/v2"
        self.ws_url = "wss://api-pub.bitfinex.com/ws/2"
        self.current_frr = 0.0
        self.chase_discount = 1.0
        self._frr_history: list[float] = []
        self._FRR_HISTORY_MAX = 60

        # Predator Matrix Tranches
        self.tranche_senior = 0.50
        self.tranche_mezzanine = 0.30
        self.tranche_tail = 0.20

        self._log(f"[{self._now()}] [User {self.user_id}] Omni-Node Initialized | {self.wallet_currency}")

    def _now(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def _wallet_currency_match(self, w_row) -> bool:
        """True if this wallet row is for self.wallet_currency (UST/USDT normalized for Bitfinex)."""
        if not isinstance(w_row, (list, tuple)) or len(w_row) < 2:
            return False
        if (w_row[0] or "").strip().lower() != "funding":
            return False
        c = (w_row[1] or "").strip().upper()
        if c == self.wallet_currency:
            return True
        if self.wallet_currency in ("UST", "USDT", "USDt") and c in ("UST", "USDT"):
            return True
        return False

    def _log(self, msg: str) -> None:
        try:
            print(msg)
        except UnicodeEncodeError:
            print(msg.encode("ascii", errors="replace").decode("ascii"))
        if self.log_lines is not None:
            self.log_lines.append(msg)

    def get_nonce(self) -> str:
        if self._shared_nonce_ref is not None:
            lst, lock = self._shared_nonce_ref
            with lock:
                next_nonce = lst[0] + 1
                # Ensure nonce is never smaller than current time (avoids 10114 after other tools used higher nonce)
                lst[0] = max(next_nonce, int(time.time() * 1000000))
                return str(lst[0])
        self._nonce = max(self._nonce + 1, int(time.time() * 1000000))
        return str(self._nonce)

    def _rebase_nonce_for_10114(self) -> None:
        """Re-base shared nonce above current time so next request is above what Bitfinex has seen (after 10114)."""
        if self._shared_nonce_ref is not None:
            lst, lock = self._shared_nonce_ref
            with lock:
                lst[0] = int(time.time() * 1000000) + 1000
        else:
            self._nonce = int(time.time() * 1000000) + 1000

    @staticmethod
    def _is_nonce_error(status: int, body: list | str) -> bool:
        """True if response indicates Bitfinex 10114 'nonce: small'."""
        if status != 200:
            if isinstance(body, str):
                try:
                    parsed = json.loads(body)
                    if isinstance(parsed, list) and len(parsed) >= 2:
                        if parsed[0] == "error" and (parsed[1] == 10114 or (len(parsed) > 2 and "nonce" in str(parsed[2]).lower())):
                            return True
                except Exception:
                    if "10114" in body or "nonce" in body.lower():
                        return True
            return False
        if isinstance(body, list) and len(body) >= 2 and body[0] == "error":
            if body[1] == 10114 or (len(body) > 2 and "nonce" in str(body[2]).lower()):
                return True
        return False

    def _generate_signature(self, path: str, nonce: str, body: dict) -> str:
        payload = json.dumps(body) if body else "{}"
        signature = f"/api/v2{path}{nonce}{payload}"
        return hmac.new(self.api_secret.encode(), signature.encode(), hashlib.sha384).hexdigest()

    async def _api_request(self, path: str, body: dict = None) -> dict | list | None:
        async def _do_request() -> tuple[dict | list | None, bool]:
            nonce = await get_next_nonce(self.redis_pool, self.api_key) if self.redis_pool else self.get_nonce()
            headers = {
                "bfx-nonce": nonce,
                "bfx-apikey": self.api_key,
                "bfx-signature": self._generate_signature(path, nonce, body or {}),
                "Content-Type": "application/json"
            }
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(f"{self.rest_url}{path}", headers=headers, json=body, timeout=10) as resp:
                        if resp.status != 200:
                            body_text = await resp.text()
                            self._log(f"[User {self.user_id}] API {path} → HTTP {resp.status} | {body_text[:200]}")
                            is_nonce = self._is_nonce_error(resp.status, body_text)
                            return (None, is_nonce)
                        out = await resp.json()
                        # Bitfinex can return ["error", code, "message"] with 200
                        if isinstance(out, list) and len(out) > 0 and out[0] == "error":
                            self._log(f"[User {self.user_id}] API {path} → error response: {out}")
                            is_nonce = self._is_nonce_error(200, out)
                            return (None, is_nonce)
                        return (out, False)
            except Exception as e:
                self._log(f"[User {self.user_id}] API Error ({path}): {e}")
                return (None, False)

        async def _run():
            max_nonce_retries = 3
            for attempt in range(1 + max_nonce_retries):
                result, is_10114 = await _do_request()
                if result is not None:
                    return result
                if is_10114 and attempt < max_nonce_retries:
                    self._rebase_nonce_for_10114()
                    await asyncio.sleep(1.0 + attempt * 0.5)
                    continue
                return None
            return None

        if self._bfx_request_lock is not None:
            async with self._bfx_request_lock:
                return await _run()
        return await _run()

    # --- 🟢 Dashboard Heartbeat ---
    async def broadcast_status(self):
        """Pushes current engine metrics to Redis for the Frontend Dashboard."""
        if not self.redis_pool:
            return
        try:
            status_data = {
                "user_id": self.user_id,
                "asset": self.wallet_currency,
                "waroc": f"{self.waroc * 365 * 100:.2f}%",
                "loaned": f"{self.total_loaned:,.2f}",
                "balance": f"{self.total_balance:,.2f}",
                "utilization": f"{(self.total_loaned / self.total_balance * 100) if self.total_balance > 0 else 0:.1f}%",
                "market_apr": f"{self.current_frr * 365 * 100:.2f}%",
                "timestamp": time.time()
            }
            key = f"status:{self.user_id}:{self.wallet_currency}"
            await self.redis_pool.set(key, json.dumps(status_data), ex=120)
        except Exception as e:
            print(f"Broadcast Error: {e}")

    async def market_listener(self):
        """Listens to live FRR updates via WebSocket."""
        await asyncio.sleep(2) 
        while True:
            try:
                async with websockets.connect(self.ws_url) as ws:
                    await ws.send(json.dumps({"event": "subscribe", "channel": "ticker", "symbol": self.symbol}))
                    while True:
                        msg = await ws.recv()
                        data = json.loads(msg)
                        if isinstance(data, list) and data[1] != "hb" and len(data[1]) == 16:
                            self.current_frr = float(data[1][0])
                            self._frr_history.append(self.current_frr)
                            if len(self._frr_history) > self._FRR_HISTORY_MAX:
                                self._frr_history = self._frr_history[-self._FRR_HISTORY_MAX:]
            except Exception:
                await asyncio.sleep(5) 

    async def fetch_instant_snapshot(self):
        """Immediate REST snapshot of market rates."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.rest_url}/tickers?symbols={self.symbol}", timeout=5) as resp:
                    data = await resp.json()
                    if data and len(data) > 0:
                        self.current_frr = float(data[0][1])
                        return True
        except Exception: pass
        return False

    async def cancel_stuck_senior_orders(self) -> bool:
        """Cancels 2-day orders open for > 7 minutes."""
        offers = await self._api_request(f"/auth/r/funding/offers/{self.symbol}", {})
        if not offers or (isinstance(offers, list) and len(offers) > 0 and offers[0] == 'error'): 
            return False
        now_ms = int(time.time() * 1000)
        canceled_any = False
        for off in offers:
            try:
                offer_id = off[0]
                mts_updated = next((v for v in off if isinstance(v, (int, float)) and v > 1500000000000), now_ms)
                age_mins = abs(now_ms - mts_updated) / 60000.0
                if age_mins >= 7.0:
                    await self._api_request("/auth/w/funding/offer/cancel", {"id": offer_id})
                    canceled_any = True
            except Exception: continue 
        if canceled_any:
            self.chase_discount = max(self.chase_discount * 0.99, 0.90)
        return canceled_any

    def _wallet_balance(self, w: list) -> float:
        """Read balance from wallet row: w[2]=BALANCE, w[4]=AVAILABLE_BALANCE. Prefer w[2]; fallback to w[4] if w[2] is 0/None."""
        try:
            bal = float(w[2]) if len(w) > 2 and w[2] is not None else 0.0
            if bal > 0:
                return bal
            if len(w) > 4 and w[4] is not None:
                return float(w[4])
        except (TypeError, ValueError, IndexError):
            pass
        return 0.0

    async def check_portfolio_status(self) -> tuple[float, float, float]:
        """Calculates current WAROC, balance, and loaned amounts."""
        credits = await self._api_request(f"/auth/r/funding/credits/{self.symbol}", {})
        wallets = await self._api_request("/auth/r/wallets", {})

        self.total_balance = 0.0
        if wallets and isinstance(wallets, list) and (len(wallets) == 0 or wallets[0] != "error"):
            for w in wallets:
                if not isinstance(w, (list, tuple)) or len(w) < 3:
                    continue
                if self._wallet_currency_match(w):
                    self.total_balance = self._wallet_balance(w)
                    break
        elif not wallets:
            self._log(f"[User {self.user_id}] check_portfolio_status: no wallets response (API failed or empty).")

        self.total_loaned = 0.0
        weighted_rate_sum = 0.0
        if credits and isinstance(credits, list) and credits[0] != 'error':
            for c in credits:
                try:
                    amount, rate = float(c[5]), float(c[11])
                    self.total_loaned += amount
                    weighted_rate_sum += (amount * rate)
                except Exception: continue

        self.waroc = (weighted_rate_sum / self.total_loaned) if self.total_loaned > 0 else 0.0
        utilization = (self.total_loaned / self.total_balance) if self.total_balance > 0 else 0.0

        # 🟢 Log: when lent, show WAROC + loaned; when idle, show balance + friendly message (throttled)
        if self.total_loaned > 0:
            self._log(f"[{self._now()}] [User {self.user_id}] 📊 [{self.wallet_currency}] WAROC: {self.waroc*365*100:>5.2f}% APR | Loaned: {self.total_loaned:,.2f}")
        else:
            now_ts = time.time()
            if now_ts - self._last_idle_log_time >= 300:  # at most once every 5 min per currency
                self._last_idle_log_time = now_ts
                self._log(f"[{self._now()}] [User {self.user_id}] 📊 [{self.wallet_currency}] Idle | Balance: {self.total_balance:,.2f} | No active loans (offers may be pending)")
        await self.broadcast_status()
        
        return self.waroc, utilization, self.total_loaned

    async def get_ai_insight(self, wapr: float, util: float, total_loaned: float) -> str:
        """Asynchronous Gemini insights with geo-fallback logic."""
        if not self.ai_enabled: return "AI Offline."
        try:
            prompt = f"Asset: {self.wallet_currency}, Rate: {self.current_frr*365*100:.2f}%, Util: {util*100:.1f}%. Provide a 1-sentence Wall St style insight."
            response = await asyncio.to_thread(self.ai_client.models.generate_content, model="gemini-2.0-flash", contents=prompt)
            return response.text.strip()
        except Exception:
            return f"⚠️ [Local Quant Mode]: FRR Base: {self.current_frr*365*100:.2f}% APR | Matrix Active."

    async def deploy_matrix(self, full_rebuild=False):
        """Calculates and submits the 50/30/20 Predator Matrix grid."""
        if full_rebuild:
            wapr, util, loaned = await self.check_portfolio_status()
            ai_task = asyncio.ensure_future(self.get_ai_insight(wapr, util, loaned))
            await self._api_request("/auth/w/funding/offer/cancel/all", {"currency": self.wallet_currency})
            await asyncio.sleep(1)
            try:
                insight = await asyncio.wait_for(ai_task, timeout=3)
            except (asyncio.TimeoutError, Exception):
                insight = f"AI Offline."
            self._log(f"\n[{self._now()}] [User {self.user_id}] 📈 Strategy: {insight}")

        # Same as check script: /auth/r/wallets → w[0]=TYPE, w[1]=CURRENCY, w[2]=BALANCE, w[4]=AVAILABLE_BALANCE
        wallets = await self._api_request("/auth/r/wallets", {})
        if not wallets or (isinstance(wallets, list) and len(wallets) > 0 and wallets[0] == "error"):
            self._log(f"[User {self.user_id}] deploy_matrix: no wallets (API failed or error response); skipping.")
            return
        balance = 0.0
        raw_available = None
        for w in wallets or []:
            if not isinstance(w, (list, tuple)) or not self._wallet_currency_match(w):
                continue
            balance = self._wallet_balance(w)
            if len(w) > 4 and w[4] is not None:
                try:
                    raw_available = float(w[4])
                except (TypeError, ValueError):
                    raw_available = None
            break
        # Only deploy when w[4] (deposit available) is valid; do not use balance - in_offers (overestimates and causes "not enough balance in deposit wallet")
        if raw_available is None or raw_available < self.MIN_ORDER_AMT:
            self._log(f"[{self._now()}] [User {self.user_id}] [{self.wallet_currency}] Skip deploy: w[4] missing or < MIN; need deposit available from API (w[2]={balance:,.4f} w[4]={raw_available!r} MIN={self.MIN_ORDER_AMT:,.4f})")
            return
        # Safety margin (99%) to avoid Bitfinex 10001 "not enough balance in deposit wallet"
        available = min(raw_available, math.floor(raw_available * 0.99 * 1e4) / 1e4)
        if available < self.MIN_ORDER_AMT:
            return
        self._log(f"[{self._now()}] [User {self.user_id}] [{self.wallet_currency}] Available = {available:,.4f} (w[4]={raw_available:,.4f}, 99% margin)")

        # Strategy B+F: only place when current rate >= 24h rolling median AND showing upward momentum
        # Momentum filter: current rate above short-term average of recent ticks (backtest: +2.3% APY)
        if _strategy_b_gate_enabled() and self.redis_pool:
            try:
                snapshot = await get_oracle_snapshot(self.redis_pool)
                medians = (snapshot or {}).get("frr_24h_median") or {}
                median_val = medians.get(self.symbol)
                if median_val is not None and self.current_frr < median_val:
                    self._log(f"[{self._now()}] [User {self.user_id}] Strategy B: {self.symbol} rate {self.current_frr:.6f} below 24h median {median_val:.6f}; skipping this cycle.")
                    return
                if len(self._frr_history) >= 10:
                    sma = sum(self._frr_history[-30:]) / len(self._frr_history[-30:])
                    if self.current_frr < sma and not full_rebuild:
                        self._log(f"[{self._now()}] [User {self.user_id}] Momentum: {self.symbol} rate {self.current_frr:.6f} < SMA {sma:.6f}; waiting for uptick.")
                        return
            except Exception as e:
                self._log(f"[{self._now()}] [User {self.user_id}] Strategy B oracle check error: {e}; placing anyway.")

        safe_frr = max(self.current_frr, 0.0001) * self.chase_discount
        self._log(f"[{self._now()}] [User {self.user_id}] 🌊 [{self.wallet_currency}] Deploying | Target Rate: {safe_frr*365*100:.2f}% | Discount: {self.chase_discount:.3f}")
        self._log(f"[{self._now()}] [User {self.user_id}] 🌊 [{self.wallet_currency}] Grid Available: {available:,.4f}")
        ops, running_balance = [], available

        def _round_down_4(x: float) -> float:
            """Round down to 4 decimals so sum of orders never exceeds available."""
            return math.floor(x * 1e4) / 1e4

        # Tranche Calculation
        if full_rebuild and available < self.SWEEP_AMT:
            amt_s, amt_m, amt_t = available, 0.0, 0.0
        else:
            amt_s = available * self.tranche_senior if full_rebuild else running_balance
            amt_m = available * self.tranche_mezzanine if full_rebuild else 0.0
            amt_t = available * self.tranche_tail if full_rebuild else 0.0

        # 1. Senior Tranche (2-Day)
        if amt_s >= self.MIN_ORDER_AMT:
            grid_s = min(max(int(amt_s / (2000 / self.spot_price)), 3), 15)
            single_amt = max(amt_s / grid_s, self.MIN_ORDER_AMT)
            for r in np.linspace(safe_frr, safe_frr * 1.05, grid_s):
                if running_balance < self.MIN_ORDER_AMT:
                    break
                order_amt = single_amt if running_balance - single_amt >= self.MIN_ORDER_AMT else running_balance
                order_amt = _round_down_4(min(order_amt, running_balance))
                if order_amt < self.MIN_ORDER_AMT:
                    break
                ops.append({"type": "LIMIT", "symbol": self.symbol, "amount": f"{order_amt:.4f}", "rate": str(round(r, 8)), "period": 2, "label": "SENIOR"})
                running_balance -= order_amt

        # 2. Mezzanine (30-Day)
        if full_rebuild and running_balance >= self.MIN_ORDER_AMT and amt_m > 0:
            for r in np.linspace(self.current_frr * 1.5, self.current_frr * 2.8, 4):
                if running_balance < self.MIN_ORDER_AMT:
                    break
                order_amt = max(amt_m / 4, self.MIN_ORDER_AMT)
                order_amt = _round_down_4(min(order_amt, running_balance))
                if order_amt < self.MIN_ORDER_AMT:
                    break
                ops.append({"type": "LIMIT", "symbol": self.symbol, "amount": f"{order_amt:.4f}", "rate": str(round(r, 8)), "period": 30, "flags": 64, "label": "MEZZANINE"})
                running_balance -= order_amt

        # 3. Tail Trap (60-Day)
        if full_rebuild and running_balance >= self.MIN_ORDER_AMT and amt_t > 0:
            for r in np.geomspace(self.current_frr * 3.0, self.current_frr * 6.0, 3):
                if running_balance < self.MIN_ORDER_AMT:
                    break
                order_amt = self.MIN_ORDER_AMT if running_balance > (self.MIN_ORDER_AMT * 2) else running_balance
                order_amt = _round_down_4(min(order_amt, running_balance))
                if order_amt < self.MIN_ORDER_AMT:
                    break
                ops.append({"type": "LIMIT", "symbol": self.symbol, "amount": f"{order_amt:.4f}", "rate": str(round(r, 8)), "period": 60, "flags": 64, "label": "TAIL TRAP"})
                running_balance -= order_amt

        consecutive_fails = 0
        for op in ops:
            lbl = op.pop("label")
            resp = await self._api_request("/auth/w/funding/offer/submit", op)
            if resp is None:
                consecutive_fails += 1
                self._log(f"   └─ [{self.wallet_currency}] SUBMIT FAILED | {lbl} | amount={op.get('amount')} (check Bitfinex API response)")
                if consecutive_fails >= 3:
                    self._log(f"[{self._now()}] [User {self.user_id}] [{self.wallet_currency}] Stopping order submission after {consecutive_fails} consecutive failures.")
                    break
            else:
                consecutive_fails = 0
                self._log(f"   └─ [{self.wallet_currency}] TICKET ISSUED | {lbl:<10} | {float(op['amount']):>10,.4f} | {float(op['rate'])*365*100:>6.2f}% APR | {op.get('period', 0)}d")
            await asyncio.sleep(0.15)

    async def run_loop(self):
        """Main Task Engine loop."""
        asyncio.create_task(self.market_listener())
        await self.fetch_instant_snapshot()
        await self.deploy_matrix(full_rebuild=True)
        heartbeat = 0
        consecutive_loop_errors = 0
        try:
            while True:
                try:
                    for _ in range(3):
                        await asyncio.sleep(60)
                        await self.check_portfolio_status()
                    heartbeat += 3
                    if await self.cancel_stuck_senior_orders():
                        await self.deploy_matrix(full_rebuild=False)
                        consecutive_loop_errors = 0
                        continue
                    if heartbeat % 12 == 0:
                        await self.deploy_matrix(full_rebuild=True)
                    else:
                        await self.deploy_matrix(full_rebuild=False)
                    consecutive_loop_errors = 0
                except asyncio.CancelledError:
                    raise
                except Exception as e:
                    consecutive_loop_errors += 1
                    self._log(f"[{self._now()}] [User {self.user_id}] [{self.wallet_currency}] Loop error ({consecutive_loop_errors}): {type(e).__name__}: {e}")
                    if consecutive_loop_errors >= 5:
                        self._log(f"[{self._now()}] [User {self.user_id}] [{self.wallet_currency}] Too many consecutive errors; exiting engine.")
                        return
                    await asyncio.sleep(30)
        except asyncio.CancelledError:
            await self._api_request("/auth/w/funding/offer/cancel/all", {"currency": self.wallet_currency})
            raise

class PortfolioManager:
    """Orchestrates multiple asset engines for a user. Uses a shared nonce and a single asyncio lock per key so only one Bitfinex request is in flight at a time (avoids 10114 nonce: small)."""
    def __init__(self, user_id: int, api_key: str, api_secret: str, gemini_key: str, redis_pool=None, log_lines: list | None = None):
        self.user_id, self.api_key, self.api_secret, self.gemini_key = user_id, api_key, api_secret, gemini_key
        self.redis_pool = redis_pool
        self.log_lines = log_lines
        self._nonce = int(time.time() * 1000000)
        self._shared_nonce = [self._nonce]
        self._nonce_lock = threading.Lock()
        self._bfx_request_lock = asyncio.Lock()

    async def _rebase_nonce_for_10114(self) -> int:
        """Re-base nonce above current time for PortfolioManager. Returns the rebased nonce value."""
        # Use a much larger buffer (30 seconds) to ensure nonce is always valid
        now_us = int(time.time() * 1000000) + 30000000  # 30 seconds buffer
        if self.redis_pool:
            try:
                from services.bitfinex_nonce import nonce_key
                key = nonce_key(self.api_key)
                await self.redis_pool.set(key, str(now_us), ex=86400)
                log_msg = f"[{datetime.now().strftime('%H:%M:%S')}] [User {self.user_id}] Rebased Redis nonce {key} to {now_us}"
                print(log_msg)
                if self.log_lines is not None:
                    self.log_lines.append(log_msg)
            except Exception as e:
                log_msg = f"[{datetime.now().strftime('%H:%M:%S')}] [User {self.user_id}] Failed to rebase Redis nonce: {e}"
                print(log_msg)
                if self.log_lines is not None:
                    self.log_lines.append(log_msg)
        self._nonce = now_us
        self._shared_nonce[0] = now_us
        return now_us

    async def _api_request(self, path: str, body: dict = None, use_rebased_nonce: int | None = None):
        rebased_nonce_ref = [use_rebased_nonce]  # Use list for mutable closure
        async def _do_request() -> tuple[dict | list | None, bool]:
            if rebased_nonce_ref[0] is not None:
                # Use the rebased nonce directly for retry
                nonce = str(rebased_nonce_ref[0])
            elif self.redis_pool:
                nonce = await get_next_nonce(self.redis_pool, self.api_key)
            else:
                self._nonce = max(self._nonce + 1, int(time.time() * 1000000))
                nonce = str(self._nonce)
            body_str = json.dumps(body or {}) if body else "{}"
            headers = {"bfx-nonce": nonce, "bfx-apikey": self.api_key, "Content-Type": "application/json",
                       "bfx-signature": hmac.new(self.api_secret.encode(), f"/api/v2{path}{nonce}{body_str}".encode(), hashlib.sha384).hexdigest()}
            try:
                async with aiohttp.ClientSession() as s:
                    async with s.post(f"https://api.bitfinex.com/v2{path}", headers=headers, json=body, timeout=10) as r:
                        if r.status != 200:
                            body_text = await r.text()
                            log_msg = f"[{datetime.now().strftime('%H:%M:%S')}] [User {self.user_id}] API {path} → HTTP {r.status} | {body_text[:200]}"
                            print(log_msg)
                            if self.log_lines is not None:
                                self.log_lines.append(log_msg)
                            is_nonce = WallStreet_Omni_FullEngine._is_nonce_error(r.status, body_text)
                            return (None, is_nonce)
                        out = await r.json()
                        if isinstance(out, list) and len(out) > 0 and out[0] == "error":
                            log_msg = f"[{datetime.now().strftime('%H:%M:%S')}] [User {self.user_id}] API {path} → error response: {out}"
                            print(log_msg)
                            if self.log_lines is not None:
                                self.log_lines.append(log_msg)
                            is_nonce = WallStreet_Omni_FullEngine._is_nonce_error(200, out)
                            return (None, is_nonce)
                        return (out, False)
            except Exception as e:
                log_msg = f"[{datetime.now().strftime('%H:%M:%S')}] [User {self.user_id}] API Error ({path}): {e}"
                print(log_msg)
                if self.log_lines is not None:
                    self.log_lines.append(log_msg)
                return (None, False)
        
        async def _run():
            max_nonce_retries = 3
            for attempt in range(1 + max_nonce_retries):
                result, is_10114 = await _do_request()
                if result is not None:
                    return result
                if is_10114 and attempt < max_nonce_retries:
                    log_msg = f"[{datetime.now().strftime('%H:%M:%S')}] [User {self.user_id}] Nonce error (attempt {attempt+1}/{max_nonce_retries}), rebasing..."
                    print(log_msg)
                    if self.log_lines is not None:
                        self.log_lines.append(log_msg)
                    rebased_nonce_us = await self._rebase_nonce_for_10114()
                    rebased_nonce_ref[0] = rebased_nonce_us
                    await asyncio.sleep(1.0 + attempt * 0.5)
                    continue
                return None
            return None
        
        async with self._bfx_request_lock:
            return await _run()

    async def scan_and_launch(self):
        msg = f"[{datetime.now().strftime('%H:%M:%S')}] [User {self.user_id}] [SCANNER] Initializing..."
        print(msg)
        if self.log_lines is not None:
            self.log_lines.append(msg)
        # _api_request already handles the lock internally, don't double-lock
        wallets = await self._api_request("/auth/r/wallets", {})
        # Sync shared_nonce so engines (when not using Redis) continue from same counter
        if not self.redis_pool:
            self._shared_nonce[0] = self._nonce
        if not wallets or (isinstance(wallets, list) and len(wallets) > 0 and wallets[0] == "error"):
            err = f"[{datetime.now().strftime('%H:%M:%S')}] [User {self.user_id}] [SCANNER] Failure: Could not fetch wallets (API error or empty)."
            print(err)
            if self.log_lines is not None:
                self.log_lines.append(err)
            return

        def _pm_balance(w):
            try:
                b = float(w[2]) if len(w) > 2 and w[2] is not None else 0.0
                if b > 0:
                    return b
                return float(w[4]) if len(w) > 4 and w[4] is not None else 0.0
            except (TypeError, ValueError, IndexError):
                return 0.0

        funding = [w for w in wallets if isinstance(w, (list, tuple)) and len(w) >= 3 and w[0] == "funding" and _pm_balance(w) > 0]
        if not funding:
            err = f"[{datetime.now().strftime('%H:%M:%S')}] [User {self.user_id}] [SCANNER] No funding wallets with balance. Nothing to deploy."
            print(err)
            if self.log_lines is not None:
                self.log_lines.append(err)
            return
        msg2 = f"[{datetime.now().strftime('%H:%M:%S')}] [User {self.user_id}] [SCANNER] Found {len(funding)} funding wallet(s). Starting trading engines..."
        print(msg2)
        if self.log_lines is not None:
            self.log_lines.append(msg2)
        engine_coros = []
        shared_nonce_ref = (self._shared_nonce, self._nonce_lock)
        for w in funding:
            engine = WallStreet_Omni_FullEngine(
                self.user_id, self.api_key, self.api_secret, self.gemini_key, w[1], 1.0,
                self.redis_pool, self.log_lines, shared_nonce_ref=shared_nonce_ref,
                bfx_request_lock=self._bfx_request_lock,
            )
            engine_coros.append(engine.run_loop())
        if engine_coros:
            results = await asyncio.gather(*engine_coros, return_exceptions=True)
            for i, r in enumerate(results):
                if isinstance(r, Exception) and not isinstance(r, asyncio.CancelledError):
                    curr = funding[i][1] if i < len(funding) else "?"
                    err = f"[{datetime.now().strftime('%H:%M:%S')}] [User {self.user_id}] [{curr}] Engine exited with error: {type(r).__name__}: {r}"
                    print(err)
                    if self.log_lines is not None:
                        self.log_lines.append(err)


def _load_iqm_baselines() -> dict:
    """Load data/iqm_baselines.json; return {} if missing or invalid."""
    try:
        if IQM_BASELINES_PATH.exists():
            with open(IQM_BASELINES_PATH, encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _norm_currency(s: str) -> str:
    """Normalize currency so USDt / USDT / UST → UST; dashboard-style for consistent totals."""
    if not s:
        return ""
    c = (s or "").strip().upper()
    if c in ("USDT", "UST"):  # USDt uppercases to USDT
        return "UST"
    return c


def _funding_balances_from_wallets(wallets: list) -> dict[str, float]:
    """Funding wallet balance per currency (normalized keys). Uses w[2] = total balance."""
    result: dict[str, float] = {}
    for w in wallets or []:
        try:
            if (w[0] or "").strip().lower() != "funding":
                continue
            curr = _norm_currency(w[1])
            bal = float(w[2])
            if curr:
                result[curr] = result.get(curr, 0.0) + bal
        except (IndexError, TypeError, ValueError):
            continue
    return result


def _aggregate_credits_per_currency(credits_data: list) -> dict[str, float]:
    """Aggregate funding credits: symbol at 1 (fUSD/fUST), amount at 5. Normalized keys."""
    result: dict[str, float] = {}
    for row in credits_data or []:
        try:
            if not isinstance(row, (list, tuple)) or len(row) <= 5:
                continue
            sym = (row[1] or "").strip().upper()
            if sym.startswith("F"):
                sym = sym[1:]
            curr = _norm_currency(sym)
            amount = float(row[5]) if row[5] is not None else 0.0
            if curr:
                result[curr] = result.get(curr, 0.0) + amount
        except (TypeError, ValueError, IndexError):
            continue
    return result


def _aggregate_offers_per_currency(offers_data: list) -> dict[str, float]:
    """Aggregate funding offers: symbol at 1, amount at 4. Normalized keys."""
    result: dict[str, float] = {}
    for row in offers_data or []:
        try:
            if not isinstance(row, (list, tuple)) or len(row) <= 4:
                continue
            sym = (row[1] or "").strip().upper()
            if sym.startswith("F"):
                sym = sym[1:]
            curr = _norm_currency(sym)
            amount = float(row[4]) if row[4] is not None else 0.0
            if curr:
                result[curr] = result.get(curr, 0.0) + amount
        except (TypeError, ValueError, IndexError):
            continue
    return result


class PortfolioOrchestrator:
    """
    IQM orchestrator: reads market data from Redis Oracle only, uses square-root
    allocation of 100 slots, logarithmic ladder, shadow drip (20% now). Optional AI via AI_ContextInjector.
    Uses lag_minutes_composite from iqm_baselines.json to front-run lending rate spikes (place ladder ~N min ahead).
    """
    def __init__(self, user_record, redis_pool):
        self.user_id = getattr(user_record, "id", user_record.get("id"))
        self.api_key = getattr(user_record, "api_key", user_record.get("api_key"))
        self.api_secret = getattr(user_record, "api_secret", user_record.get("api_secret"))
        self.gemini_key = getattr(user_record, "gemini_key", user_record.get("gemini_key")) or ""
        raw_tier = (getattr(user_record, "plan_tier", user_record.get("plan_tier")) or "trial").strip().lower()
        self.tier = "ai_ultra" if raw_tier in ("ai ultra", "ai_ultra") else raw_tier.replace(" ", "_")
        self.redis = redis_pool
        self._nonce = int(time.time() * 1000000)
        cfg = PLAN_CONFIG.get(self.tier, PLAN_CONFIG["free"])
        self.sleep_seconds = cfg["sleep_minutes"] * 60
        self.ai = AI_ContextInjector(self.gemini_key)
        self.rest_url = "https://api.bitfinex.com/v2"
        self.log_lines = getattr(user_record, "log_lines", user_record.get("log_lines"))
        self._local_quant_status_logged = False
        self._lag_frontrun_logged = False
        self._terminal_lines: list[str] = []  # flushed to Redis each cycle for Terminal tab
        baselines = _load_iqm_baselines()
        lag = baselines.get("lag_minutes_composite_after_btc_surge")
        self.lag_minutes_composite = int(lag) if lag is not None and isinstance(lag, (int, float)) else DEFAULT_LAG_MINUTES_COMPOSITE

    def _log(self, msg: str) -> None:
        try:
            print(msg)
        except Exception:
            pass
        self._terminal_lines.append(msg)
        if self.log_lines is not None:
            self.log_lines.append(msg)

    def _now(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    async def _api_request(self, path: str, body: dict = None):
        self._nonce += 1
        payload = json.dumps(body or {}, separators=(",", ":"))
        sig = hmac.new(
            self.api_secret.encode(),
            f"/api/v2{path}{self._nonce}{payload}".encode(),
            hashlib.sha384,
        ).hexdigest()
        headers = {
            "bfx-nonce": str(self._nonce),
            "bfx-apikey": self.api_key,
            "bfx-signature": sig,
            "Content-Type": "application/json",
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.rest_url}{path}", headers=headers, json=body, timeout=10) as resp:
                    if resp.status != 200:
                        return None
                    return await resp.json()
        except Exception as e:
            self._log(f"[{self._now()}] [User {self.user_id}] API Error ({path}): {e}")
            return None

    def _spot_price(self, currency: str) -> float:
        if currency in ("USD", "UST", "USDT"):
            return 1.0
        if currency == "BTC":
            return 50000.0
        return 1.0

    def _min_order_amt(self, currency: str) -> float:
        return max(0.0001, MIN_ORDER_USD / self._spot_price(currency))

    def _regime_from_v_sigma(self, v_sigma: float) -> str:
        if v_sigma >= 2.0:
            return "HIGH_VOLATILITY"
        if v_sigma <= 0.8:
            return "LOW_DEMAND"
        return "NEUTRAL"

    # Terminal logs: keep last N lines, key TTL (cost-effective at scale)
    _TERMINAL_MAX_LINES = 100
    _TERMINAL_KEY_TTL_SEC = 3600  # 1 hour

    async def _flush_terminal(self, summary_dict: dict) -> None:
        """Push accumulated log lines and summary to Redis for the Terminal tab."""
        if not self._terminal_lines and not summary_dict:
            return
        try:
            key_logs = f"terminal_logs:{self.user_id}"
            if self._terminal_lines:
                for line in self._terminal_lines:
                    await self.redis.rpush(key_logs, line)
                await self.redis.ltrim(key_logs, -self._TERMINAL_MAX_LINES, -1)
                await self.redis.expire(key_logs, self._TERMINAL_KEY_TTL_SEC)
            key_summary = f"terminal_summary:{self.user_id}"
            await self.redis.set(key_summary, json.dumps(summary_dict), ex=120)
        except Exception as e:
            try:
                print(f"[{self._now()}] [User {self.user_id}] Terminal flush error: {e}")
            except Exception:
                pass
        finally:
            self._terminal_lines.clear()

    async def scan_and_launch(self) -> None:
        """Single long-running loop: read Oracle, wallets, IQM alloc, ladder, shadow drip 20%, AI, sleep."""
        slots_per_curr = []
        while True:
            try:
                snapshot = await get_oracle_snapshot(self.redis)
                if not snapshot:
                    if not self._local_quant_status_logged:
                        self._log(f"[{self._now()}] [User {self.user_id}] [IQM] Running on Local Quant Engine.")
                        self._local_quant_status_logged = True
                    v_sigma = 1.0
                    frr = {}
                else:
                    ts = snapshot.get("ts") or 0
                    if (time.time() * 1000 - ts) > ORACLE_STALE_SEC * 1000:
                        self._log(f"[{self._now()}] [User {self.user_id}] [IQM] Oracle snapshot stale; using anyway.")
                    v_sigma = float(snapshot.get("btc_v_sigma", 1.0))
                    frr = snapshot.get("frr") or {}
                    self._local_quant_status_logged = False

                wallets = await self._api_request("/auth/r/wallets", {})
                if not wallets or (isinstance(wallets, list) and len(wallets) > 0 and wallets[0] == "error"):
                    await asyncio.sleep(self.sleep_seconds)
                    continue
                credits_data = await self._api_request("/auth/r/funding/credits", {})
                offers_data = await self._api_request("/auth/r/funding/offers", {})

                funding_balances = _funding_balances_from_wallets(wallets)
                credits_per_currency = _aggregate_credits_per_currency(
                    credits_data if isinstance(credits_data, list) else []
                )
                offers_per_currency = _aggregate_offers_per_currency(
                    offers_data if isinstance(offers_data, list) else []
                )
                all_currencies = set(funding_balances) | set(credits_per_currency) | set(offers_per_currency)
                idle_per_currency: dict[str, float] = {}
                for c in all_currencies:
                    bal = funding_balances.get(c, 0.0)
                    lent = credits_per_currency.get(c, 0.0)
                    in_offers = offers_per_currency.get(c, 0.0)
                    idle_per_currency[c] = max(0.0, bal - lent - in_offers)

                funding = []
                for curr, idle in idle_per_currency.items():
                    if idle <= 0:
                        continue
                    min_amt = self._min_order_amt(curr)
                    if idle >= min_amt:
                        funding.append((curr, idle, self._spot_price(curr)))

                if not funding:
                    self._log(f"[{self._now()}] [User {self.user_id}] [IQM] No funding balance.")
                    await asyncio.sleep(self.sleep_seconds)
                    continue

                total_sqrt = sum(np.sqrt(av * sp) for _, av, sp in funding)
                if total_sqrt <= 0:
                    await asyncio.sleep(self.sleep_seconds)
                    continue

                chunk_usd = SHATTER_CHUNK_USD_HIGH_VOL if v_sigma > 2.0 else SHATTER_CHUNK_USD_NORMAL
                slots_per_curr = []
                for curr, avail, sp in funding:
                    weight = np.sqrt(avail * sp) / total_sqrt
                    n_slots = max(1, min(MAX_ORDER_SLOTS, int(round(weight * MAX_ORDER_SLOTS))))
                    min_amt = self._min_order_amt(curr)
                    chunk_curr = chunk_usd / sp
                    amt_per_order = max(min_amt, min(avail / n_slots, chunk_curr))
                    slots_per_curr.append((curr, n_slots, amt_per_order, avail, frr.get(f"f{curr}", 0.0001)))

                # Strategy B: only place for currencies where rate >= 24h rolling median (gate off if STRATEGY_B_GATE_ENABLED=0)
                if _strategy_b_gate_enabled():
                    medians = (snapshot or {}).get("frr_24h_median") or {}
                    slots_above_median = []
                    for curr, n_slots, amt_per_order, avail, rate in slots_per_curr:
                        sym = f"f{curr}"
                        median_val = medians.get(sym)
                        if median_val is not None and rate < median_val:
                            self._log(f"[{self._now()}] [User {self.user_id}] Strategy B: skipping {sym} (rate {rate:.6f} < 24h median {median_val:.6f})")
                            continue
                        slots_above_median.append((curr, n_slots, amt_per_order, avail, rate))
                    if not slots_above_median:
                        self._log(f"[{self._now()}] [User {self.user_id}] Strategy B: all rates below 24h median; skipping this cycle.")
                        await asyncio.sleep(self.sleep_seconds)
                        continue
                    slots_per_curr = slots_above_median

                # Front-run lending rate spike: nudge base rate up by lag-based bump (look N min ahead)
                lag_min = self.lag_minutes_composite
                if not self._lag_frontrun_logged:
                    self._log(f"[{self._now()}] [User {self.user_id}] [IQM] Front-running rate ladder by lag_minutes_composite={lag_min} min.")
                    self._lag_frontrun_logged = True
                regime = self._regime_from_v_sigma(v_sigma)
                self._log(f"[{self._now()}] [User {self.user_id}] Strategy: IQM Square-Root | Regime: {regime} (v_σ={v_sigma:.2f}) | Front-run: {lag_min} min")
                front_run_bump = min(0.05, lag_min / 1000.0)  # e.g. 34 min => 3.4%
                r_base_forward = 1.0 + front_run_bump

                all_ops = []
                for curr, n_slots, amt_per_order, avail, rate in slots_per_curr:
                    sym = f"f{curr}"
                    min_amt = self._min_order_amt(curr)
                    r_base = max(rate, 0.0001) * r_base_forward  # institutional: 34 min ahead
                    rates_log = np.geomspace(r_base, r_base * 1.2, max(2, min(n_slots, 20)))
                    remaining = avail
                    for r in rates_log:
                        if remaining < min_amt:
                            break
                        order_amt = min(amt_per_order, remaining)
                        remaining -= order_amt
                        all_ops.append({"type": "LIMIT", "symbol": sym, "amount": str(round(order_amt, 4)), "rate": str(round(float(r), 8)), "period": 2})

                drip_count = max(1, int(len(all_ops) * SHADOW_DRIP_FRACTION))
                for i, op in enumerate(all_ops[:drip_count]):
                    await self._api_request("/auth/w/funding/offer/submit", op)
                    self._log(f"   └─ [IQM] {op['symbol']} | {float(op['amount']):>10,.4f} | {float(op['rate'])*365*100:>6.2f}% APR")
                    await asyncio.sleep(0.15)
                total_drip_usd = sum(
                    float(all_ops[i]["amount"]) * self._spot_price(all_ops[i]["symbol"][1:])
                    for i in range(drip_count)
                )
                self._log(f"[{self._now()}] [User {self.user_id}] Deployed: {drip_count} offers (Shadow Drip 20%) | ~{total_drip_usd:,.0f} USD")

                assets_summary = " | ".join(
                    f"{c} {av:,.0f} @ {rate*365*100:.1f}%" for c, _, _, av, rate in slots_per_curr
                )
                insight = await self.ai.get_insight(v_sigma, assets_summary)
                try:
                    await self.redis.set(f"iqm:insight:{self.user_id}", json.dumps({"insight": insight, "ts": time.time()}), ex=300)
                except Exception:
                    pass
                self._log(f"[{self._now()}] [User {self.user_id}] 📈 {insight}")

                aprs = [float(op["rate"]) * 365 * 100 for op in all_ops]
                idle_usd = {c: idle_per_currency[c] * self._spot_price(c) for c in idle_per_currency}
                offers_total_usd = sum(
                    float(all_ops[i]["amount"]) * self._spot_price(all_ops[i]["symbol"][1:])
                    for i in range(drip_count)
                )
                summary = {
                    "strategy": "IQM Square-Root",
                    "regime": regime,
                    "v_sigma": round(v_sigma, 4),
                    "lag_minutes_composite": self.lag_minutes_composite,
                    "idle_per_currency_usd": idle_usd,
                    "offers_this_cycle": {"count": drip_count, "total_usd": round(offers_total_usd, 2)},
                    "apr_ladder_min": round(min(aprs), 2) if aprs else 0,
                    "apr_ladder_max": round(max(aprs), 2) if aprs else 0,
                    "next_rebalance_sec": self.sleep_seconds,
                    "last_insight": insight,
                    "status": "deploying",
                }
                await self._flush_terminal(summary)

            except asyncio.CancelledError:
                for curr, _, _, _, _ in slots_per_curr:
                    try:
                        await self._api_request("/auth/w/funding/offer/cancel/all", {"currency": curr})
                    except Exception:
                        pass
                raise
            except Exception as e:
                self._log(f"[{self._now()}] [User {self.user_id}] [IQM] Error: {e}")
            await asyncio.sleep(self.sleep_seconds)