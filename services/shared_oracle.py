"""
Shared Market Oracle: runs once for the entire server.
Fetches BTC volume and FRR rates from Bitfinex public API every 60s and stores
a JSON snapshot in Redis. All user engines read from this cache to avoid public API spam.
"""
import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

TICKERS_URL = "https://api.bitfinex.com/v2/tickers"
ORACLE_SNAPSHOT_KEY = "oracle:snapshot"
ORACLE_SNAPSHOT_TTL_SEC = 120
ORACLE_LOOP_INTERVAL_SEC = 60
# Strategy B: 24h rolling median of FRR (1 sample/min → 1440 samples)
ORACLE_FRR_HISTORY_LEN = 1440
ORACLE_FRR_MEDIAN_MIN_SAMPLES = 60
# Default baseline when data/iqm_baselines.json is missing (e.g. before bootstrap).
DEFAULT_BTC_VOL_BASELINE = 3500.0
IQM_BASELINES_PATH = Path(__file__).resolve().parent.parent / "data" / "iqm_baselines.json"


def _parse_tickers(data: list) -> tuple[dict[str, float], float]:
    """
    Parse Bitfinex v2 tickers response.
    Returns (frr_rates, btc_volume): frr_rates keys e.g. fUSD, fUST, fBTC; btc_volume from tBTCUSD.
    Ticker array: [SYMBOL, BID, BID_SIZE, ASK, ASK_SIZE, DAILY_CHANGE, DAILY_CHANGE_PERC, LAST_PRICE, VOLUME, HIGH, LOW]
    For funding tickers, index 1 is typically the FRR (bid rate).
    """
    frr_rates: dict[str, float] = {}
    btc_volume = 0.0
    for row in data or []:
        if not isinstance(row, list) or len(row) < 9:
            continue
        try:
            sym = row[0] if isinstance(row[0], str) else str(row[0])
            if sym.startswith("f"):
                # Funding: rate at index 1
                frr_rates[sym] = float(row[1])
            elif sym == "tBTCUSD":
                # Trading: volume at index 8
                btc_volume = float(row[8]) if row[8] is not None else 0.0
        except (TypeError, ValueError, IndexError):
            continue
    return frr_rates, btc_volume


def _compute_v_sigma(btc_volume: float, baseline: float = DEFAULT_BTC_VOL_BASELINE) -> float:
    """Volatility multiplier: current_volume / baseline, clamped to [0.5, 3.0]."""
    if baseline <= 0:
        return 1.0
    raw = btc_volume / baseline
    return min(3.0, max(0.5, raw))


def _regime_from_v_sigma(v_sigma: float) -> str:
    if v_sigma >= 2.0:
        return "HIGH_VOLATILITY"
    if v_sigma <= 0.8:
        return "LOW_DEMAND"
    return "NEUTRAL"


def _median(values: list[float]) -> float | None:
    """Return median of non-empty list; None if empty."""
    if not values:
        return None
    s = sorted(values)
    n = len(s)
    return (s[n // 2] + s[(n - 1) // 2]) / 2.0


class GlobalMarketOracle:
    """
    Runs once for the entire server. Fetches public data to save API limits.
    Reads data/iqm_baselines.json for btc_vol_sma_180d; uses that as volume baseline for v_sigma.
    """
    def __init__(self, redis_pool: Any):
        self.redis = redis_pool
        self.btc_v_sigma = 1.0
        self.frr_rates: dict[str, float] = {}
        self.frr_24h_median: dict[str, float] = {}
        self.regime = "NEUTRAL"
        self.BTC_VOL_BASELINE = DEFAULT_BTC_VOL_BASELINE
        if IQM_BASELINES_PATH.exists():
            try:
                with open(IQM_BASELINES_PATH, encoding="utf-8") as f:
                    data = json.load(f)
                val = data.get("btc_vol_sma_180d")
                if val is not None and isinstance(val, (int, float)) and val > 0:
                    self.BTC_VOL_BASELINE = float(val)
                    logger.info("Oracle using baseline from %s: %.4f", IQM_BASELINES_PATH.name, self.BTC_VOL_BASELINE)
            except Exception as e:
                logger.warning("Could not load %s: %s; using default baseline.", IQM_BASELINES_PATH, e)

    async def _fetch_tickers(self) -> tuple[dict[str, float], float]:
        symbols = "fUSD,fUST,fBTC,tBTCUSD"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{TICKERS_URL}?symbols={symbols}", timeout=10) as resp:
                    if resp.status != 200:
                        return self.frr_rates, 0.0
                    data = await resp.json()
                    return _parse_tickers(data)
        except Exception as e:
            logger.warning("Oracle tickers fetch failed: %s", e)
            return self.frr_rates, 0.0

    async def _write_snapshot(self) -> None:
        ts_ms = int(time.time() * 1000)
        payload = {
            "btc_v_sigma": self.btc_v_sigma,
            "regime": self.regime,
            "frr": self.frr_rates,
            "frr_24h_median": self.frr_24h_median,
            "ts": ts_ms,
        }
        try:
            raw = json.dumps(payload)
            await self.redis.set(ORACLE_SNAPSHOT_KEY, raw, ex=ORACLE_SNAPSHOT_TTL_SEC)
        except Exception as e:
            logger.warning("Oracle Redis set failed: %s", e)

    async def _update_frr_24h_median(self) -> None:
        """Append current FRR to Redis history per symbol; compute 24h rolling median."""
        self.frr_24h_median = {}
        for sym, rate in self.frr_rates.items():
            key = f"oracle:frr_history:{sym}"
            try:
                await self.redis.rpush(key, str(rate))
                await self.redis.ltrim(key, -ORACLE_FRR_HISTORY_LEN, -1)
                raw_list = await self.redis.lrange(key, 0, -1)
                vals = []
                for s in raw_list or []:
                    try:
                        vals.append(float(s))
                    except (TypeError, ValueError):
                        continue
                if len(vals) >= ORACLE_FRR_MEDIAN_MIN_SAMPLES:
                    med = _median(vals)
                    if med is not None:
                        self.frr_24h_median[sym] = med
            except Exception as e:
                logger.warning("Oracle FRR history/median failed for %s: %s", sym, e)

    async def run_forever(self) -> None:
        while True:
            try:
                frr_rates, btc_volume = await self._fetch_tickers()
                if frr_rates:
                    self.frr_rates = frr_rates
                    await self._update_frr_24h_median()
                self.btc_v_sigma = _compute_v_sigma(btc_volume, self.BTC_VOL_BASELINE)
                self.regime = _regime_from_v_sigma(self.btc_v_sigma)
                await self._write_snapshot()
            except Exception as e:
                logger.exception("Oracle loop error: %s", e)
            await asyncio.sleep(ORACLE_LOOP_INTERVAL_SEC)


async def get_oracle_snapshot(redis_pool: Any) -> dict | None:
    """
    Read oracle snapshot from Redis. Returns None if missing or invalid.
    Callers can use ts to detect staleness (e.g. ts older than 2 min).
    """
    try:
        raw = await redis_pool.get(ORACLE_SNAPSHOT_KEY)
        if not raw:
            return None
        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")
        return json.loads(raw)
    except Exception:
        return None
