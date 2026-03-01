"""
IQM Data Pipeline: download 6 months of 1m candles from Bitfinex and compute baselines.
Saves CSVs to data/historical/ and data/iqm_baselines.json for GlobalMarketOracle.
"""
import asyncio
import csv
import json
import logging
from pathlib import Path

import aiohttp

# Resolve project root (parent of scripts/)
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
HISTORICAL_DIR = DATA_DIR / "historical"
BASELINES_PATH = DATA_DIR / "iqm_baselines.json"

CANDLES_BASE = "https://api.bitfinex.com/v2/candles"
LIMIT_PER_REQUEST = 1000
RATE_LIMIT_SLEEP_SEC = 2
DAYS_BACK = 180

# Trading pair: standard hist. Funding: Bitfinex uses period (e.g. p30) or aggregated a30:p2:p30.
CANDLE_KEYS = [
    "trade:1m:tBTCUSD",   # Trading pair
    "trade:1m:fUSD:a30:p2:p30",   # Funding fUSD 1m candles (aggregate)
    "trade:1m:fUST:a30:p2:p30",   # Funding fUST (Tether) 1m candles
]

logger = logging.getLogger(__name__)


def _csv_path(symbol_like: str) -> Path:
    """Map candle key to a short filename."""
    if "tBTCUSD" in symbol_like:
        name = "tBTCUSD_1m"
    elif "fUSD" in symbol_like:
        name = "fUSD_1m"
    elif "fUST" in symbol_like:
        name = "fUSDT_1m"
    else:
        name = symbol_like.replace(":", "_").replace(".", "_")
    return HISTORICAL_DIR / f"{name}.csv"


def _display_name(candle_key: str) -> str:
    """Short label for progress (e.g. BTC, fUSD, fUSDT)."""
    if "tBTCUSD" in candle_key:
        return "BTC"
    if "fUSD" in candle_key and "fUST" not in candle_key:
        return "fUSD"
    if "fUST" in candle_key:
        return "fUSDT"
    return candle_key.split(":")[-1]


def _load_existing_csv(out_path: Path) -> list[list]:
    """Load existing CSV rows as [MTS, O, C, H, L, VOL] (numeric). Returns [] if missing or empty."""
    if not out_path.exists():
        return []
    rows: list[list] = []
    with open(out_path, newline="", encoding="utf-8") as f:
        r = csv.reader(f)
        next(r, None)  # header
        for line in r:
            if len(line) >= 6:
                try:
                    rows.append([int(line[0]), float(line[1]), float(line[2]), float(line[3]), float(line[4]), float(line[5])])
                except (ValueError, TypeError):
                    pass
    return rows


def _write_csv(out_path: Path, all_rows: list[list]) -> None:
    """Sort by MTS and write full CSV."""
    all_rows.sort(key=lambda r: r[0])
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["MTS", "OPEN", "CLOSE", "HIGH", "LOW", "VOLUME"])
        w.writerows(all_rows)


async def _fetch_chunk(
    session: aiohttp.ClientSession,
    candle_key: str,
    end_ms: int | None,
    limit: int = LIMIT_PER_REQUEST,
) -> list[list]:
    """Fetch one chunk of candles (hist, descending by MTS). Returns list of [MTS, O, C, H, L, VOL]."""
    url = f"{CANDLES_BASE}/{candle_key}/hist"
    params = {"limit": limit, "sort": -1}
    if end_ms is not None:
        params["end"] = end_ms
    try:
        async with session.get(url, params=params, timeout=30) as resp:
            if resp.status != 200:
                text = await resp.text()
                logger.warning("%s hist status=%s body=%s", candle_key, resp.status, text[:200])
                return []
            data = await resp.json()
            return data if isinstance(data, list) else []
    except Exception as e:
        logger.warning("%s fetch error: %s", candle_key, e)
        return []


def _ms_to_days(ms: float) -> float:
    return ms / (24 * 60 * 60 * 1000)


async def download_6m_candles() -> None:
    """
    Download 1m candles for tBTCUSD, fUSD, and fUSDT (fUST) for the last 180 days.
    Uses timestamp-based pagination (1000 per request) and 2s sleep to respect 30 req/min.
    Saves CSVs under data/historical/. Resume: if CSV exists, continues from last timestamp.
    """
    import time as _t
    HISTORICAL_DIR.mkdir(parents=True, exist_ok=True)
    end_ms = int(_t.time() * 1000)
    start_ms = end_ms - (DAYS_BACK * 24 * 60 * 60 * 1000)
    total_target = DAYS_BACK * 24 * 60  # 259200

    async with aiohttp.ClientSession() as session:
        for candle_key in CANDLE_KEYS:
            out_path = _csv_path(candle_key)
            label = _display_name(candle_key)

            # Resume: load existing and determine backfill / catch-up range
            all_rows = _load_existing_csv(out_path)
            existing_min = min(r[0] for r in all_rows) if all_rows else None
            existing_max = max(r[0] for r in all_rows) if all_rows else None
            if all_rows:
                logger.info("Resume %s: %d rows (%.1f–%.1f days ago).", label, len(all_rows), _ms_to_days(end_ms - existing_max), _ms_to_days(end_ms - existing_min))

            # Phase 1: Backfill from start_ms up to existing_min - 1 (if we have a gap at the start)
            if existing_min is not None and existing_min > start_ms:
                current_end = existing_min - 1
                while current_end > start_ms:
                    chunk = await _fetch_chunk(session, candle_key, current_end, LIMIT_PER_REQUEST)
                    await asyncio.sleep(RATE_LIMIT_SLEEP_SEC)
                    if not chunk:
                        break
                    all_rows.extend(chunk)
                    min_mts = min(r[0] for r in chunk)
                    current_end = min_mts - 1
                    _write_csv(out_path, all_rows)
                    days_remaining = max(0.0, _ms_to_days(min_mts - start_ms))
                    logger.info("Downloaded %d/%d candles for %s (Days remaining: %.1f).", len(all_rows), total_target, label, days_remaining)
                    if min_mts <= start_ms:
                        break

            # Phase 2: Catch-up from existing_max + 1 to end_ms (or full download if no existing)
            if existing_max is not None and existing_max >= end_ms:
                logger.info("Done %s: %d rows (up to date).", label, len(all_rows))
                continue
            current_end = end_ms
            if existing_max is not None:
                # Catch-up: fetch only candles newer than existing_max
                original_max = existing_max
                while True:
                    chunk = await _fetch_chunk(session, candle_key, current_end, LIMIT_PER_REQUEST)
                    await asyncio.sleep(RATE_LIMIT_SLEEP_SEC)
                    if not chunk:
                        break
                    new_rows = [r for r in chunk if r[0] > original_max]
                    if not new_rows:
                        break
                    all_rows.extend(new_rows)
                    existing_max = max(r[0] for r in all_rows)
                    _write_csv(out_path, all_rows)
                    logger.info("Downloaded %d/%d candles for %s (catch-up; Days remaining: 0).", len(all_rows), total_target, label)
                    min_mts = min(r[0] for r in chunk)
                    current_end = min_mts - 1
                    if min_mts <= original_max:
                        break
                continue

            # Full download (no existing data)
            while current_end > start_ms:
                chunk = await _fetch_chunk(session, candle_key, current_end, LIMIT_PER_REQUEST)
                await asyncio.sleep(RATE_LIMIT_SLEEP_SEC)
                if not chunk:
                    break
                all_rows.extend(chunk)
                min_mts = min(r[0] for r in chunk)
                current_end = min_mts - 1
                _write_csv(out_path, all_rows)
                days_remaining = max(0.0, _ms_to_days(min_mts - start_ms))
                logger.info("Downloaded %d/%d candles for %s (Days remaining: %.1f).", len(all_rows), total_target, label, days_remaining)
                if min_mts <= start_ms:
                    break

            if not all_rows:
                logger.warning("No candles for %s; skipping CSV.", candle_key)
                continue
            logger.info("Wrote %s: %d rows (%s).", out_path.name, len(all_rows), candle_key)


def calculate_baselines() -> None:
    """
    Read historical CSVs and compute institutional baselines:
    - BTC 180-day SMA of minute volume
    - Pearson correlation between BTC volume and fUSD/fUSDT lending rates
    - Lag estimate (minutes) from BTC volume surge to subsequent lending-rate spike
    Writes data/iqm_baselines.json.
    """
    try:
        import pandas as pd
        import numpy as np
    except ImportError:
        raise RuntimeError("pandas is required for calculate_baselines(); pip install pandas")

    btc_path = HISTORICAL_DIR / "tBTCUSD_1m.csv"
    fusd_path = HISTORICAL_DIR / "fUSD_1m.csv"
    fust_path = HISTORICAL_DIR / "fUSDT_1m.csv"
    for p in (btc_path, fusd_path, fust_path):
        if not p.exists():
            raise FileNotFoundError(f"Missing {p}; run download_6m_candles() first.")

    btc = pd.read_csv(btc_path, usecols=["MTS", "VOLUME"]).rename(columns={"VOLUME": "btc_volume"})
    fusd = pd.read_csv(fusd_path, usecols=["MTS", "CLOSE"]).rename(columns={"CLOSE": "fusd_rate"})
    fust = pd.read_csv(fust_path, usecols=["MTS", "CLOSE"]).rename(columns={"CLOSE": "fusdt_rate"})
    merged = btc.merge(fusd, on="MTS", how="inner").merge(fust, on="MTS", how="inner").sort_values("MTS")

    if merged.empty:
        raise ValueError("No overlapping timestamps across BTC/fUSD/fUSDT CSVs.")

    merged["btc_volume"] = merged["btc_volume"].astype(float)
    merged["fusd_rate"] = merged["fusd_rate"].astype(float)
    merged["fusdt_rate"] = merged["fusdt_rate"].astype(float)

    # 180-day SMA of BTC minute volume over the loaded dataset
    sma = float(merged["btc_volume"].mean())

    corr_btc_fusd = float(merged["btc_volume"].corr(merged["fusd_rate"]))
    corr_btc_fusdt = float(merged["btc_volume"].corr(merged["fusdt_rate"]))

    def _estimate_lag_minutes(df: pd.DataFrame, rate_col: str, horizon_min: int = 360) -> tuple[int | None, float | None]:
        """
        Event-based lag:
        - volume surge: z-score >= 2.0
        - rate spike: minute delta >= 95th percentile of positive deltas
        For each surge, find first later spike within horizon and take median lag.
        """
        vol = df["btc_volume"]
        vol_std = float(vol.std(ddof=0))
        if vol_std <= 0:
            return None, None

        vol_z = (vol - float(vol.mean())) / vol_std
        surge_idx = np.where(vol_z.values >= 2.0)[0]
        if len(surge_idx) == 0:
            return None, None

        rate_delta = df[rate_col].diff().fillna(0.0)
        positive = rate_delta[rate_delta > 0]
        if positive.empty:
            return None, None
        spike_threshold = float(positive.quantile(0.95))
        spike_idx = np.where(rate_delta.values >= spike_threshold)[0]
        if len(spike_idx) == 0:
            return None, spike_threshold

        lags: list[int] = []
        for s in surge_idx:
            later_spikes = spike_idx[spike_idx >= s]
            if len(later_spikes) == 0:
                continue
            lag = int(later_spikes[0] - s)
            if 0 <= lag <= horizon_min:
                lags.append(lag)

        if not lags:
            return None, spike_threshold
        return int(np.median(lags)), spike_threshold

    lag_fusd_min, fusd_spike_threshold = _estimate_lag_minutes(merged, "fusd_rate")
    lag_fusdt_min, fusdt_spike_threshold = _estimate_lag_minutes(merged, "fusdt_rate")

    lag_values = [x for x in (lag_fusd_min, lag_fusdt_min) if x is not None]
    lag_composite = int(round(sum(lag_values) / len(lag_values))) if lag_values else None

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    payload = {
        "btc_vol_sma_180d": sma,
        "rows_analyzed": int(len(merged)),
        "pearson_corr_btc_volume_fusd_rate": corr_btc_fusd,
        "pearson_corr_btc_volume_fusdt_rate": corr_btc_fusdt,
        "lag_minutes_fusd_after_btc_surge": lag_fusd_min,
        "lag_minutes_fusdt_after_btc_surge": lag_fusdt_min,
        "lag_minutes_composite_after_btc_surge": lag_composite,
        "rate_spike_threshold_fusd_delta": fusd_spike_threshold,
        "rate_spike_threshold_fusdt_delta": fusdt_spike_threshold,
    }
    with open(BASELINES_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)
    logger.info(
        "Wrote %s | SMA=%.6f corr(fUSD)=%.6f corr(fUSDT)=%.6f lag=%s min",
        BASELINES_PATH,
        sma,
        corr_btc_fusd,
        corr_btc_fusdt,
        lag_composite,
    )


def run_pipeline() -> None:
    """Run download then baselines (sync wrapper for use from start_system)."""
    asyncio.run(download_6m_candles())
    calculate_baselines()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_pipeline()
