"""
Bitfinex 6m 1m data: find strong correlations, design strategies focused on daily/typical
conditions (not top 1% peaks). Backtest with 100k USD, 2-day orders; compare APY to current.
Run from project root: python scripts/strategy_correlation_and_backtest.py
"""
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "historical"

try:
    import pandas as pd
    import numpy as np
except ImportError:
    print("Need pandas and numpy. pip install pandas numpy")
    sys.exit(1)


def load_series(csv_path: Path, rate_col: str = "CLOSE") -> pd.DataFrame:
    """Load CSV with MTS and rate column; add UTC time features."""
    df = pd.read_csv(csv_path, usecols=["MTS", rate_col])
    df = df.rename(columns={rate_col: "rate"})
    df["MTS"] = pd.to_numeric(df["MTS"], errors="coerce").astype("int64")
    df = df.dropna().sort_values("MTS")
    df["dt"] = pd.to_datetime(df["MTS"], unit="ms", utc=True)
    df["utc_hour"] = df["dt"].dt.hour
    df["utc_dow"] = df["dt"].dt.dayofweek
    df["minute_of_day"] = df["dt"].dt.hour * 60 + df["dt"].dt.minute
    return df


def main():
    fusd_path = DATA_DIR / "fUSD_1m.csv"
    fust_path = DATA_DIR / "fUSDT_1m.csv"
    btc_path = DATA_DIR / "tBTCUSD_1m.csv"
    if not fusd_path.exists():
        print("Missing fUSD_1m.csv. Run data_pipeline first.")
        return 1

    # Load fUSD (primary for 100k USD test)
    fusd = load_series(fusd_path)
    if fusd.empty or len(fusd) < 1000:
        print("Insufficient fUSD data.")
        return 1

    # --- 1) CORRELATIONS (daily/typical: use full series, then median-by-hour) ---
    print("=" * 70)
    print("1. CORRELATIONS (6m 1m fUSD data)")
    print("=" * 70)

    r = fusd["rate"]
    # Autocorrelation (lag 1 min, 60 min, 1440 min)
    ac1 = r.autocorr(lag=1)
    ac60 = r.autocorr(lag=60) if len(r) > 60 else None
    ac1440 = r.autocorr(lag=1440) if len(r) > 1440 else None
    print(f"  Rate autocorr lag 1 min:    {ac1:.4f}")
    print(f"  Rate autocorr lag 60 min:   {ac60:.4f}" if ac60 is not None else "  Rate autocorr lag 60 min:   N/A")
    print(f"  Rate autocorr lag 1440 min: {ac1440:.4f}" if ac1440 is not None else "  Rate autocorr lag 1440 min: N/A")

    # By UTC hour (median rate per hour) - strong for "time of day" strategy
    by_hour = fusd.groupby("utc_hour")["rate"].agg(["median", "mean", "count"])
    by_hour = by_hour.sort_values("median", ascending=False)
    best_hours = by_hour.index[:6].tolist()
    worst_hours = by_hour.index[-6:].tolist()
    print(f"  Best 6 UTC hours (median rate): {best_hours} -> median rate {by_hour.iloc[:6]['median'].mean():.6f}")
    print(f"  Worst 6 UTC hours:              {worst_hours} -> median rate {by_hour.iloc[-6:]['median'].mean():.6f}")

    # By day of week
    by_dow = fusd.groupby("utc_dow")["rate"].median()
    best_dow = by_dow.idxmax()
    print(f"  Best day-of-week (0=Mon): {int(best_dow)} (median rate {by_dow.max():.6f})")

    # fUSD vs fUSDT (if available) - lead/lag
    if fust_path.exists():
        fust = load_series(fust_path)
        merged = fusd[["MTS", "rate"]].merge(fust[["MTS", "rate"]], on="MTS", suffixes=("_usd", "_ust"))
        if len(merged) > 100:
            corr = merged["rate_usd"].corr(merged["rate_ust"])
            print(f"  fUSD vs fUSDT (same minute):  {corr:.4f}")

    # Rolling: rate vs above 24h median (for "place when above median" strategy)
    fusd["roll24h_median"] = r.rolling(24 * 60, min_periods=60).median()
    fusd["above_median24"] = (r >= fusd["roll24h_median"]).astype(int)
    pct_above = fusd["above_median24"].mean()
    print(f"  % of minutes rate >= 24h rolling median: {pct_above*100:.1f}%")

    # Exclude top 1% to get "typical daily" stats
    r_no_top1 = r[r <= r.quantile(0.99)]
    typical_mean = r_no_top1.mean()
    typical_median = r_no_top1.median()
    print(f"  Typical (excl. top 1%): mean rate {typical_mean:.6f}, median {typical_median:.6f}")
    print()

    # --- 2) STRATEGIES (2-day orders, 100k USD) ---
    # We simulate: every 2 days we "place" one order. Placement minute is chosen by strategy.
    # Rate at that minute = daily rate; 2-day order earns 2*rate (simple). APY from series of 2*rate.
    ORDER_DAYS = 2
    MIN_PER_ORDER = ORDER_DAYS * 24 * 60  # 2880 minutes between placements
    principal = 100_000.0

    # Build placement windows: start index every 2880 minutes
    n = len(fusd)
    n_windows = max(1, n // MIN_PER_ORDER)
    windows = []  # list of (start_idx, end_idx)
    for i in range(n_windows):
        start = i * MIN_PER_ORDER
        end = min(start + MIN_PER_ORDER, n)
        if end - start < 60:  # need at least 1 hour of data in window
            break
        windows.append((start, end))

    def apy_from_daily_rates(rates_list):
        """Given list of daily rates at placement, compute APY (2-day orders, compound)."""
        if not rates_list:
            return 0.0
        # Each 2-day period: growth = 1 + 2*r (simple interest for 2 days)
        growth = 1.0
        for r in rates_list:
            growth *= 1.0 + 2.0 * r
        days = len(rates_list) * ORDER_DAYS
        if days <= 0:
            return 0.0
        # Annualize
        apy = (growth ** (365.0 / days)) - 1.0
        return apy * 100.0

    # Strategy 0: Baseline (place at start of each window) - "current" behavior
    rates_baseline = [fusd["rate"].iloc[w[0]] for w in windows]
    apy_baseline = apy_from_daily_rates(rates_baseline)

    # Strategy 1: Time-of-day - place at the first minute of the best UTC hour if in window
    # Best hour from median: use hour with highest median
    best_utc_hour = int(by_hour.index[0])
    best_minute_of_day = best_utc_hour * 60
    rates_tod = []
    for start, end in windows:
        window_df = fusd.iloc[start:end]
        # Find first row in this window that is in the best hour
        in_best = window_df[window_df["utc_hour"] == best_utc_hour]
        if not in_best.empty:
            r_place = in_best["rate"].iloc[0]
        else:
            # Fallback: use median rate of window (avoid worst hours if possible)
            r_place = window_df["rate"].median()
        rates_tod.append(r_place)
    apy_tod = apy_from_daily_rates(rates_tod)

    # Strategy 2: Place when rate >= 24h rolling median (within window, take first such minute)
    rates_above_med = []
    for start, end in windows:
        window_df = fusd.iloc[start:end].copy()
        if window_df["roll24h_median"].isna().all():
            r_place = window_df["rate"].median()
        else:
            above = window_df[window_df["rate"] >= window_df["roll24h_median"]]
            if not above.empty:
                r_place = above["rate"].iloc[0]
            else:
                r_place = window_df["rate"].max()  # take best in window
        rates_above_med.append(r_place)
    apy_above_med = apy_from_daily_rates(rates_above_med)

    # Strategy 3: Avoid worst 6 hours - place at first minute that is NOT in worst hours
    rates_avoid_low = []
    for start, end in windows:
        window_df = fusd.iloc[start:end]
        ok = window_df[~window_df["utc_hour"].isin(worst_hours)]
        if not ok.empty:
            r_place = ok["rate"].iloc[0]
        else:
            r_place = window_df["rate"].median()
        rates_avoid_low.append(r_place)
    apy_avoid_low = apy_from_daily_rates(rates_avoid_low)

    # Strategy 4: Place at median minute of window (reduces variance; "typical daily")
    rates_median_minute = []
    for start, end in windows:
        window_df = fusd.iloc[start:end]
        mid = start + (end - start) // 2
        r_place = fusd["rate"].iloc[mid]
        rates_median_minute.append(r_place)
    apy_median_minute = apy_from_daily_rates(rates_median_minute)

    # Strategy 5: Combined - only place when rate >= 24h median AND in best 6 hours
    rates_combined = []
    for start, end in windows:
        window_df = fusd.iloc[start:end]
        above = window_df[window_df["rate"] >= window_df["roll24h_median"]]
        in_best = above[above["utc_hour"].isin(best_hours)]
        if not in_best.empty:
            r_place = in_best["rate"].iloc[0]
        elif not above.empty:
            r_place = above["rate"].iloc[0]
        else:
            r_place = window_df["rate"].max()
        rates_combined.append(r_place)
    apy_combined = apy_from_daily_rates(rates_combined)

    # Current strategy (1.13x bump) - same as baseline but with 1.13 multiplier
    apy_current_gross = apy_from_daily_rates([r * 1.13 for r in rates_baseline])

    # --- 3) REPORT ---
    print("=" * 70)
    print("2. BACKTEST: 100k USD, 2-day orders, 6m data (~90 placements)")
    print("=" * 70)
    print(f"  Baseline (place at window start):     APY = {apy_baseline:.2f}%")
    print(f"  Current strategy (1.13x bump):        APY = {apy_current_gross:.2f}% (gross)")
    print(f"  Strategy A - Best UTC hour ({best_utc_hour}:00):  APY = {apy_tod:.2f}%")
    print(f"  Strategy B - When rate >= 24h median:            APY = {apy_above_med:.2f}%")
    print(f"  Strategy C - Avoid worst 6 hours:                APY = {apy_avoid_low:.2f}%")
    print(f"  Strategy D - Place at mid-window (typical):     APY = {apy_median_minute:.2f}%")
    print(f"  Strategy E - Above median AND best hours:       APY = {apy_combined:.2f}%")
    print()
    print("  (Net APY after 15%% Bitfinex fee: multiply gross by 0.85)")
    print()

    # Best of new strategies vs current
    candidates = [
        ("Time-of-day (best hour)", apy_tod),
        ("Above 24h median", apy_above_med),
        ("Avoid worst hours", apy_avoid_low),
        ("Mid-window typical", apy_median_minute),
        ("Above median + best hours", apy_combined),
    ]
    best_name, best_apy = max(candidates, key=lambda x: x[1])
    print("=" * 70)
    print("3. RECOMMENDATION (daily/typical focus)")
    print("=" * 70)
    if best_apy > apy_current_gross:
        print(f"  Best alternative: {best_name} -> APY {best_apy:.2f}% (higher than current {apy_current_gross:.2f}%)")
    else:
        print(f"  Current 1.13x strategy remains best: {apy_current_gross:.2f}%")
        print(f"  Best alternative: {best_name} -> APY {best_apy:.2f}%")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
