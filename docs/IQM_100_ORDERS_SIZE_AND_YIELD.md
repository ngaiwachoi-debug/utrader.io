# IQM Strategy: Ideal Size and Yield for 100 Orders (6‑Month Baseline)

Based on the **current bot strategy** and the **Bitfinex lending market 6‑month 1‑minute data** (used in `data/iqm_baselines.json` and `scripts/data_pipeline.py`), here are the ideal notional sizes and yield expectations for **USDT** and **USD** when using **100 orders**.

---

## 1. Which engine uses 100 orders?

- **IQM path** (`PortfolioOrchestrator` in `bot_engine.py`): uses `MAX_ORDER_SLOTS = 100`, square‑root allocation, and shatter chunk sizing. This is the logic that can deploy up to 100 orders.
- **Omni path** (used by the **worker** today): 50/30/20 tranches with a smaller grid (~3–22 orders). So “100 orders” applies to the **IQM** strategy in code.

Below we assume the **IQM** strategy with 100 order slots.

---

## 2. Ideal size (notional) for 100 orders

Order size is capped by **shatter chunk** (from `bot_engine.py`):

- **Normal volatility** (`v_sigma ≤ 2.0`): `SHATTER_CHUNK_USD_NORMAL = 3,000` USD per order.
- **High volatility** (`v_sigma > 2.0`): `SHATTER_CHUNK_USD_HIGH_VOL = 1,000` USD per order.

Minimum per order: `MIN_ORDER_USD = 150`.

| Currency | Regime    | Ideal total size (100 orders) | Min size (100 × min order) |
|----------|-----------|--------------------------------|-----------------------------|
| **USDT** | Normal    | **300,000 USDT**              | 15,000 USDT                |
| **USDT** | High vol  | **100,000 USDT**              | 15,000 USDT                |
| **USD**  | Normal    | **300,000 USD**               | 15,000 USD                 |
| **USD**  | High vol  | **100,000 USD**               | 15,000 USD                 |

So:

- **Ideal USDT with 100 orders:** **300,000 USDT** (normal) or **100,000 USDT** (high vol).
- **Ideal USD with 100 orders:** **300,000 USD** (normal) or **100,000 USD** (high vol).

With less than ideal size, you still get 100 orders but each order is smaller (down to 150 USD/USDT each, i.e. 15,000 total).

---

## 3. Expected yield (APR)

The 6‑month baseline does **not** output a single “expected APR” number. It provides:

- **Lag (minutes)** from BTC volume surge to lending rate spike: **fUSD 36 min**, **fUSDT 32 min**, **composite 34 min**.
- **Rate spike thresholds** (95th percentile of positive 1m rate deltas):  
  `rate_spike_threshold_fusd_delta ≈ 0.00024`, `rate_spike_threshold_fusdt_delta ≈ 0.00021`.
- **Correlations** (BTC volume vs rate): fUSD ≈ −0.007, fUSDT ≈ 0.03 (weak).

The bot uses these to **front‑run** the rate spike (place the ladder ~34 min ahead). The **yield** you get is the **volume‑weighted average rate (WAROC)** of whatever orders get filled, which depends on:

1. **Live FRR** (funding rate) at placement time.
2. **Front‑run bump**: `min(5%, lag_min / 1000)` → e.g. **~3.4%** for 34 min.
3. **Ladder**: rates from `r_base` to `r_base × 1.2` (log spacing).

So the ladder sits roughly at **FRR × (1 + bump)** to **FRR × (1 + bump) × 1.2**. With a 34‑min lag that’s about **1.034 × FRR** to **1.24 × FRR**.

- **Typical range on Bitfinex**: fUSD / fUSDT can be **~5–25% APR** in normal conditions and higher in volatile periods.
- **Rough expected yield (APR)** for the IQM 100‑order strategy:
  - **USDT:** in the range of **current fUSDT FRR × (1.03 – 1.24)** (market‑dependent).
  - **USD:** in the range of **current fUSD FRR × (1.03 – 1.24)** (market‑dependent).

So **yield is market‑dependent**; the 6‑month data says *when* rate spikes tend to follow BTC volume (lag), not a fixed APR. The strategy aims to capture that spike by placing the ladder slightly ahead of it.

---

## 4. Summary table

| Asset | Ideal size (100 orders, normal vol) | Ideal size (100 orders, high vol) | Expected yield (APR)        |
|-------|-------------------------------------|-----------------------------------|----------------------------|
| USDT  | **300,000 USDT**                    | **100,000 USDT**                  | FRR × ~1.03–1.24 (market)  |
| USD   | **300,000 USD**                     | **100,000 USD**                   | FRR × ~1.03–1.24 (market)  |

FRR = current Bitfinex funding rate (e.g. from ticker). Use live FRR for a concrete APR estimate.

---

## 5. Expected APY: 100k USDT + 100k USD

For **$100,000 USDT** and **$100,000 USD** (200k total), the strategy places a rate ladder at **r_base = FRR × 1.034** to **r_base × 1.2** (log spacing). The **volume‑weighted average rate** of the book is roughly the geometric mean of the ladder: **≈ 1.13 × FRR** (APR).

**APY** (annual percentage yield) assumes interest compounds. If we treat funding as **daily compounding**:

- **APY = (1 + APR/365)^365 − 1**

So for a given market FRR you get:

| If market FRR (APR) is | Strategy APR (≈1.13×FRR) | Expected APY (daily compound) |
|------------------------|---------------------------|--------------------------------|
| 5%                     | ~5.7%                     | **~5.8%**                      |
| 8%                     | ~9.0%                     | **~9.4%**                      |
| 10%                    | ~11.3%                    | **~12.0%**                     |
| 12%                    | ~13.6%                    | **~14.5%**                     |
| 15%                    | ~17.0%                    | **~18.5%**                     |
| 20%                    | ~22.6%                    | **~25.4%**                     |

**For 100k USDT + 100k USD:**

- **Conservative (FRR 8%):** expect **~9–9.5% APY** on the 200k (≈ **$18k–19k/year**).
- **Mid (FRR 10%):** expect **~11.5–12% APY** (≈ **$23k–24k/year**).
- **Strong (FRR 15%):** expect **~17–18.5% APY** (≈ **$34k–37k/year**).

Rates on fUSD and fUSDT can differ slightly; using each side’s current FRR gives the best estimate. The table above uses a single FRR for both; in practice you can average or use USDT FRR for the 100k USDT bucket and USD FRR for the 100k USD bucket.

---

## 6. USD vs USDT: which is better?

From the **6‑month 1m baselines** only (no live rate comparison):

| Metric | USD (fUSD) | USDT (fUSDT) |
|--------|------------|---------------|
| Correlation (BTC vol → rate) | **−0.007** (none/negative) | **+0.029** (slight positive) |
| Lag after BTC surge | **36 min** | **32 min** |
| Rate spike threshold (95th %ile) | 0.00024 | 0.00021 |

- **USDT** has a **slightly better fit** for the strategy: positive correlation (when BTC volume rises, USDT rate tends to rise) and a **shorter lag** (32 min), so the “front‑run the spike” logic is a bit more aligned with USDT.
- **USD** has almost no correlation and a 4‑minute longer lag; the same front‑run may be a bit early for USD.

In **live markets**, which side pays more varies: sometimes fUSD has higher FRR (USD scarcity), sometimes fUSDT (Tether demand for margin). So:

- **For strategy/timing (6m data):** **USDT is marginally better** (faster lag, positive correlation).
- **For yield in practice:** **Check live FRR** on Bitfinex; run **both** 100k USD and 100k USDT and let the ladder capture whichever side is hot. Splitting 200k across both is a good default.

---

## 7. Accurate APY from 6‑month downloaded data

The Bitfinex 1m funding candles (CLOSE = rate per day) were analyzed over the full 6‑month window. Run `python scripts/apy_from_6m_data.py` to reproduce.

### Raw market (no strategy)

| Asset | 1m candles | Mean daily rate | APR (simple) | APY (daily compound) |
|-------|------------|------------------|--------------|------------------------|
| **fUSD (USD)**  | ~95,000  | 0.000177 | 6.45% | **6.67%** |
| **fUSDT (USDT)**| ~105,000 | 0.000170 | 6.19% | **6.39%** |
| **50/50 combined** | —   | 0.000172 | 6.28% | **6.48%** |

### With strategy (~1.13× ladder)

Front‑run bump + ladder (1.034×–1.24×) gives effective **~1.13×** mean rate:

| Asset | Strategy APY (from 6m data) |
|-------|-----------------------------|
| **USD only (100k)**  | **~7.57%** |
| **USDT only (100k)** | **~7.25%** |
| **100k USD + 100k USDT** | **~7.35%** |

### Percentiles (USD, 6m)

- Median rate → **5.90%** raw APY; **~6.7%** strategy APY.
- 95th percentile rate → **13.82%** APR (spike periods).

So over the last 6 months, **accurate expected APY** with the strategy applied to 100k USDT + 100k USD is **~7.35%** (daily compound). In spike regimes (p95) the same strategy would have earned more; the 7.35% is a **full‑period average**.

### Fee deduction (Bitfinex)

**All APY figures above are gross (before Bitfinex fee).** They are **not** fee‑deducted.

- Bitfinex charges funding **providers (lenders)** a **15% commission** on interest earned from active funding loans (18% for hidden offers).
- **Net to lender** = gross × **0.85** (or 0.82 for hidden offers).
- LEO token holders can get up to −5% discount on this commission.

| Figure | Gross APY | Net APY (after 15% fee) |
|--------|-----------|--------------------------|
| 100k USD + 100k USDT, strategy (6m) | **~7.35%** | **~6.25%** |
| USD only, strategy (6m) | ~7.57% | ~6.43% |
| USDT only, strategy (6m) | ~7.25% | ~6.16% |
| Raw market 50/50 (6m) | 6.48% | ~5.51% |

So the **fee‑deducted (net) expected APY** for 100k USD + 100k USDT over the last 6 months is **~6.25%**, not 7.35%.
