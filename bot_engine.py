"""
bot_engine.py

Core isolated algorithmic lending engine for Bitfinex.
Enhanced with Redis Heartbeat broadcasting for the Bifinex Bot Dashboard.
Multi-tenant ready: all variables are isolated per instance.
"""

import asyncio
import aiohttp
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


class WallStreet_Omni_FullEngine:
    """
    Autonomous Crypto Lending Engine. 
    Manages funding book deployments and broadcasts live stats to Redis.
    """
    def __init__(self, user_id: int, api_key: str, api_secret: str, gemini_key: str, currency: str, spot_price: float, redis_pool=None, log_lines: list | None = None):
        self.user_id = user_id
        self.api_key = api_key
        self.api_secret = api_secret
        self.gemini_key = gemini_key
        self.redis_pool = redis_pool # 🟢 Injected Redis pool for Dashboard
        self.log_lines = log_lines  # optional list to capture lines for Whales terminal
        
        self._nonce = int(time.time() * 1000000)
        self.wallet_currency = currency
        self.symbol = f"f{currency}"
        self.spot_price = spot_price 
        
        self.MIN_ORDER_AMT = 150.0 / self.spot_price if self.spot_price > 0 else 0
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

        # Predator Matrix Tranches
        self.tranche_senior = 0.50
        self.tranche_mezzanine = 0.30
        self.tranche_tail = 0.20

        self._log(f"[{self._now()}] [User {self.user_id}] Omni-Node Initialized | {self.wallet_currency}")

    def _now(self) -> str:
        return datetime.now().strftime("%H:%M:%S")

    def _log(self, msg: str) -> None:
        try:
            print(msg)
        except UnicodeEncodeError:
            print(msg.encode("ascii", errors="replace").decode("ascii"))
        if self.log_lines is not None:
            self.log_lines.append(msg)

    def get_nonce(self) -> str:
        self._nonce += 1
        return str(self._nonce)

    def _generate_signature(self, path: str, nonce: str, body: dict) -> str:
        payload = json.dumps(body) if body else "{}"
        signature = f"/api/v2{path}{nonce}{payload}"
        return hmac.new(self.api_secret.encode(), signature.encode(), hashlib.sha384).hexdigest()

    async def _api_request(self, path: str, body: dict = None) -> dict | list | None:
        nonce = self.get_nonce()
        headers = {
            "bfx-nonce": nonce, 
            "bfx-apikey": self.api_key,
            "bfx-signature": self._generate_signature(path, nonce, body or {}),
            "Content-Type": "application/json"
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(f"{self.rest_url}{path}", headers=headers, json=body, timeout=10) as resp:
                    if resp.status != 200: return None
                    return await resp.json()
        except Exception as e:
            print(f"[User {self.user_id}] API Error ({path}): {e}")
            return None

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

    async def check_portfolio_status(self) -> tuple[float, float, float]:
        """Calculates current WAROC, balance, and loaned amounts."""
        credits = await self._api_request(f"/auth/r/funding/credits/{self.symbol}", {})
        wallets = await self._api_request("/auth/r/wallets", {})
        
        self.total_balance = 0.0
        if wallets:
            self.total_balance = next((float(w[2]) for w in wallets if w[0] == "funding" and w[1] == self.wallet_currency), 0.0)

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
            insight = await self.get_ai_insight(wapr, util, loaned)
            self._log(f"\n[{self._now()}] [User {self.user_id}] 📈 Strategy: {insight}")
            await self._api_request("/auth/w/funding/offer/cancel/all", {"currency": self.wallet_currency})
            await asyncio.sleep(2) 

        wallets = await self._api_request("/auth/r/wallets", {})
        if not wallets: return
        available = next((float(w[4]) for w in wallets if w[0] == "funding" and w[1] == self.wallet_currency), 0.0)
        if available < self.MIN_ORDER_AMT: return 

        safe_frr = max(self.current_frr, 0.0001) * self.chase_discount
        self._log(f"[{self._now()}] [User {self.user_id}] 🌊 [{self.wallet_currency}] Deploying | Target Rate: {safe_frr*365*100:.2f}% | Discount: {self.chase_discount:.3f}")
        self._log(f"[{self._now()}] [User {self.user_id}] 🌊 [{self.wallet_currency}] Grid Available: {available:,.4f}")
        ops, running_balance = [], available

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
                if running_balance < self.MIN_ORDER_AMT: break
                order_amt = single_amt if running_balance - single_amt >= self.MIN_ORDER_AMT else running_balance
                ops.append({"symbol": self.symbol, "amount": str(round(order_amt, 4)), "rate": str(round(r, 8)), "period": 2, "label": "SENIOR"})
                running_balance -= order_amt

        # 2. Mezzanine (30-Day)
        if full_rebuild and running_balance >= self.MIN_ORDER_AMT and amt_m > 0:
            for r in np.linspace(self.current_frr * 1.5, self.current_frr * 2.8, 4):
                if running_balance < self.MIN_ORDER_AMT: break
                order_amt = max(amt_m / 4, self.MIN_ORDER_AMT)
                ops.append({"symbol": self.symbol, "amount": str(round(order_amt, 4)), "rate": str(round(r, 8)), "period": 30, "flags": 64, "label": "MEZZANINE"})
                running_balance -= order_amt

        # 3. Tail Trap (60-Day)
        if full_rebuild and running_balance >= self.MIN_ORDER_AMT and amt_t > 0:
            for r in np.geomspace(self.current_frr * 3.0, self.current_frr * 6.0, 3):
                if running_balance < self.MIN_ORDER_AMT: break
                order_amt = self.MIN_ORDER_AMT if running_balance > (self.MIN_ORDER_AMT * 2) else running_balance
                ops.append({"symbol": self.symbol, "amount": str(round(order_amt, 4)), "rate": str(round(r, 8)), "period": 60, "flags": 64, "label": "TAIL TRAP"})
                running_balance -= order_amt

        for op in ops:
            lbl = op.pop("label")
            await self._api_request("/auth/w/funding/offer/submit", op)
            self._log(f"   └─ [{self.wallet_currency}] TICKET ISSUED | {lbl:<10} | {float(op['amount']):>10,.4f} | {float(op['rate'])*365*100:>6.2f}% APR | {op.get('period', 0)}d")
            await asyncio.sleep(0.15)

    async def run_loop(self):
        """Main Task Engine loop."""
        asyncio.create_task(self.market_listener())
        await self.fetch_instant_snapshot()
        await self.deploy_matrix(full_rebuild=True)
        heartbeat = 0
        try:
            while True:
                for _ in range(3):
                    await asyncio.sleep(60)
                    await self.check_portfolio_status() # Heartbeat + Redis Broadcast
                heartbeat += 3
                if await self.cancel_stuck_senior_orders():
                    await self.deploy_matrix(full_rebuild=False)
                    continue
                if heartbeat % 12 == 0: await self.deploy_matrix(full_rebuild=True)
        except asyncio.CancelledError:
            await self._api_request("/auth/w/funding/offer/cancel/all", {"currency": self.wallet_currency})
            raise

class PortfolioManager:
    """Orchestrates multiple asset engines for a user."""
    def __init__(self, user_id: int, api_key: str, api_secret: str, gemini_key: str, redis_pool=None, log_lines: list | None = None):
        self.user_id, self.api_key, self.api_secret, self.gemini_key = user_id, api_key, api_secret, gemini_key
        self.redis_pool = redis_pool
        self.log_lines = log_lines
        self._nonce = int(time.time() * 1000000)

    async def _api_request(self, path: str, body: dict = None):
        self._nonce += 1
        headers = {"bfx-nonce": str(self._nonce), "bfx-apikey": self.api_key, "Content-Type": "application/json",
                   "bfx-signature": hmac.new(self.api_secret.encode(), f"/api/v2{path}{self._nonce}{json.dumps(body or {}) if body else '{}'}".encode(), hashlib.sha384).hexdigest()}
        async with aiohttp.ClientSession() as s:
            async with s.post(f"https://api.bitfinex.com/v2{path}", headers=headers, json=body) as r:
                return await r.json() if r.status == 200 else None

    async def scan_and_launch(self):
        msg = f"[{datetime.now().strftime('%H:%M:%S')}] [User {self.user_id}] [SCANNER] Initializing..."
        print(msg)
        if self.log_lines is not None:
            self.log_lines.append(msg)
        wallets = await self._api_request("/auth/r/wallets", {})
        if not wallets:
            err = f"[{datetime.now().strftime('%H:%M:%S')}] [User {self.user_id}] [SCANNER] Failure: Could not fetch wallets (API error or empty)."
            print(err)
            if self.log_lines is not None:
                self.log_lines.append(err)
            return
        funding = [w for w in wallets if w[0] == "funding" and float(w[2]) > 0]
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
        engines = []
        for w in funding:
            engine = WallStreet_Omni_FullEngine(self.user_id, self.api_key, self.api_secret, self.gemini_key, w[1], 1.0, self.redis_pool, self.log_lines)
            engines.append(engine.run_loop())
        if engines:
            await asyncio.gather(*engines)


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

    async def _flush_terminal(self, summary_dict: dict) -> None:
        """Push accumulated log lines and summary to Redis for the Terminal tab."""
        if not self._terminal_lines and not summary_dict:
            return
        try:
            key_logs = f"terminal_logs:{self.user_id}"
            if self._terminal_lines:
                for line in self._terminal_lines:
                    await self.redis.rpush(key_logs, line)
                await self.redis.ltrim(key_logs, -300, -1)
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
                        all_ops.append({"symbol": sym, "amount": str(round(order_amt, 4)), "rate": str(round(float(r), 8)), "period": 2})

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