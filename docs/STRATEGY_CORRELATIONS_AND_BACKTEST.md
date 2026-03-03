# Strategy Correlations and Backtest (6m Bitfinex fUSD, 100k USD, 2-day orders)

Based on the Bitfinex 6-month 1-minute funding data, we search for **strong correlations**, design strategies focused on **daily/typical** conditions (not top 1% peaks), and backtest with **100k USD** and **2-day** orders to compare APY to the current strategy.

Run: `python scripts/strategy_correlation_and_backtest.py`

---

## 1. Correlations (fUSD, 6m 1m)

| Correlation | Value | Note |
|-------------|--------|------|
| **Rate autocorr (1 min)** | **0.41** | Strong: rate persists minute-to-minute |
| **Rate autocorr (60 min)** | 0.23 | Moderate: same-day momentum |
| **Rate autocorr (1440 min)** | 0.06 | Weak across days |
| **fUSD vs fUSDT (same minute)** | 0.08 | Weak |
| **Best 6 UTC hours (median rate)** | 20, 2, 6, 3, 21, 19 | Slightly higher median rate |
| **Worst 6 UTC hours** | 0, 10, 15, 8, 12, 14 | Slightly lower |
| **Best day-of-week** | Thursday (3) | Slight |
| **% minutes rate ≥ 24h rolling median** | 44.4% | Below-median minutes are more frequent |

**Takeaway:** The **strongest** signal is **rate autocorrelation** (0.41 at 1 min). So “place when rate is already above its recent level” (e.g. above 24h rolling median) uses that structure. Time-of-day and day-of-week effects exist but are small; daily/typical behaviour matters more than chasing the top 1% peaks, especially with 2-day orders.

---

## 2. Strategies (2-day orders, 100k USD, ~90 placements over 6m)

| Strategy | Description | Backtest APY (gross) | Net (×0.85) |
|----------|-------------|----------------------|--------------|
| **Baseline** | Place at start of each 2-day window | 6.55% | ~5.57% |
| **Current (1.13× bump)** | Same as baseline + front-run/ladder 1.13× | **7.43%** | **~6.32%** |
| **A – Best UTC hour** | Place at first minute of best hour (20:00) in window | 6.62% | ~5.63% |
| **B – Above 24h median** | Place at first minute in window when rate ≥ 24h rolling median | **8.42%** | **~7.16%** |
| **C – Avoid worst 6 hours** | Place at first minute not in worst UTC hours | 6.20% | ~5.27% |
| **D – Mid-window (typical)** | Place at middle of each 2-day window | 6.36% | ~5.41% |
| **E – Above median + best hours** | Place when rate ≥ 24h median and UTC hour in best 6 | 7.88% | ~6.70% |

---

## 3. Recommendation (daily/typical focus)

- **Best alternative:** **Strategy B (Above 24h median)** → **8.42% gross APY** (~7.16% net after 15% fee), about **+1% gross** vs current 7.43%.
- **Implementation idea:** Within each rebalance cycle, only submit 2-day orders when the current fUSD rate is **≥ 24h rolling median** (or wait until that condition holds). If the bot already has a 24h median (or can compute it from recent ticks), gate placement on `current_frr >= roll24h_median`; otherwise wait or skip that cycle.
- Strategy E (above median + best hours) gives 7.88% gross and is a compromise if you also want to bias toward best hours.
- Time-of-day alone (A, C) does not beat current in the backtest; the **above-median** filter is what drives the gain, consistent with the strong 1‑min autocorrelation.

---

## 4. Notes

- **Daily market vs top 1%:** The backtest uses **all** placements in the 6m window (no exclusion of peaks). Strategies B and E improve APY by selecting **better-than-median** minutes, which fits a focus on “typical daily” conditions rather than only the top 1% spikes.
- **2-day orders:** Orders are assumed locked for 2 days at the rate at placement; interest = 2 × daily rate. APY is annualized from the simulated series of 2-day returns.
- **Bitfinex fee:** All APYs above are gross; net ≈ gross × 0.85 (15% provider fee).
