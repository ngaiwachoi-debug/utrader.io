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
from datetime import datetime
from google import genai 

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
        
        # 🟢 Log and Broadcast
        self._log(f"[{self._now()}] [User {self.user_id}] 📊 [{self.wallet_currency}] WAROC: {self.waroc*365*100:>5.2f}% APR | Loaned: {self.total_loaned:,.2f}")
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
        if not wallets: return
        
        engines = []
        for w in wallets:
            if w[0] == "funding" and float(w[2]) > 0:
                engine = WallStreet_Omni_FullEngine(self.user_id, self.api_key, self.api_secret, self.gemini_key, w[1], 1.0, self.redis_pool, self.log_lines)
                engines.append(engine.run_loop())
        
        if engines:
            await asyncio.gather(*engines)