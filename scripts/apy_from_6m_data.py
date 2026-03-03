"""
Estimate APY from 6-month Bitfinex funding data (data/historical/fUSD_1m.csv, fUSDT_1m.csv).

The candle CLOSE is the funding rate (per day, decimal). So:
  APR = mean(CLOSE) * 365
  APY (daily compound) = (1 + mean(CLOSE))^365 - 1

Strategy adds front-run bump (~3.4%) and ladder 1.0x–1.2x, so effective ~1.13x market rate.
"""

import csv
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "historical"


def load_close_rates(csv_path: Path) -> list[float]:
    """Load CLOSE column (funding rate per day) from candle CSV."""
    rates = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        r = csv.DictReader(f)
        for row in r:
            try:
                rates.append(float(row["CLOSE"]))
            except (ValueError, KeyError):
                pass
    return rates


def main():
    fusd_path = DATA_DIR / "fUSD_1m.csv"
    fust_path = DATA_DIR / "fUSDT_1m.csv"

    if not fusd_path.exists() or not fust_path.exists():
        print("Missing data files. Run data_pipeline first (download_6m_candles).")
        return

    fusd_rates = load_close_rates(fusd_path)
    fust_rates = load_close_rates(fust_path)

    def stats(name: str, rates: list[float]) -> None:
        if not rates:
            print(f"{name}: no data")
            return
        n = len(rates)
        mean_r = sum(rates) / n
        sorted_r = sorted(rates)
        p50 = sorted_r[n // 2]
        p25 = sorted_r[n // 4]
        p75 = sorted_r[(3 * n) // 4]
        p95 = sorted_r[int(0.95 * n)] if n >= 20 else sorted_r[-1]

        # APR = rate (per day) * 365
        apr_mean = mean_r * 365 * 100
        apr_median = p50 * 365 * 100
        apr_p95 = p95 * 365 * 100

        # APY (daily compounding): (1 + r)^365 - 1
        apy_mean = ((1 + mean_r) ** 365 - 1) * 100
        apy_median = ((1 + p50) ** 365 - 1) * 100

        print(f"\n--- {name} (n={n:,} 1m candles) ---")
        print(f"  Rate (per day): mean={mean_r:.6f}  median={p50:.6f}  p25={p25:.6f}  p75={p75:.6f}  p95={p95:.6f}")
        print(f"  APR (simple):   mean={apr_mean:.2f}%  median={apr_median:.2f}%  p95={apr_p95:.2f}%")
        print(f"  APY (daily compound): mean={apy_mean:.2f}%  median={apy_median:.2f}%")

        # Strategy: ladder at 1.034*FRR to 1.24*FRR → effective ~1.13x
        strategy_apr = apr_mean * 1.13
        strategy_apy = ((1 + mean_r * 1.13) ** 365 - 1) * 100
        print(f"  Strategy (~1.13x): APR~{strategy_apr:.2f}%  APY~{strategy_apy:.2f}%")

    print("=" * 60)
    print("6-MONTH BITFINEX FUNDING RATE → APY (from downloaded data)")
    print("=" * 60)

    stats("fUSD (USD)", fusd_rates)
    stats("fUSDT (USDT)", fust_rates)

    # Combined (50/50 USD/USDT) for 200k allocation
    if fusd_rates and fust_rates:
        # Align by length (use min length if different)
        m = min(len(fusd_rates), len(fust_rates))
        combined_mean = (sum(fusd_rates[:m]) / m + sum(fust_rates[:m]) / m) / 2
        apr_comb = combined_mean * 365 * 100
        apy_comb = ((1 + combined_mean) ** 365 - 1) * 100
        strat_apy_comb = ((1 + combined_mean * 1.13) ** 365 - 1) * 100
        print("\n--- Combined 50% USD / 50% USDT (e.g. 100k + 100k) ---")
        print(f"  Avg daily rate: {combined_mean:.6f}")
        print(f"  APR (simple):   {apr_comb:.2f}%")
        print(f"  APY (daily compound): {apy_comb:.2f}%")
        print(f"  Strategy (~1.13x) APY: {strat_apy_comb:.2f}%")

    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
