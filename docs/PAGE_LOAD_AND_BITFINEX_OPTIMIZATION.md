# Page Load & Bitfinex Optimization (1000 Traders)

This doc identifies why the dashboard can still feel slow and what to improve: **Bitfinex API usage**, **duplicate or combinable calls**, **full request flow**, and **calculations that can move to the frontend** without changing backend data.

---

## 1. Current Bitfinex API usage (backend)

### 1.1 Per-user endpoints

| Backend path | Bitfinex calls | Cache key | When it runs |
|--------------|----------------|-----------|--------------|
| **Wallets** (`_get_wallet_data` → `_portfolio_allocation_snapshot`) | `wallets()`, `funding_credits()`, `funding_offers()` (3 in parallel), then `_fetch_ticker_prices()` (public tickers) | `KEY_WALLETS` (90s TTL) | Fold, GET /wallets/{id} |
| **Lending** (`_get_lending_stats_data` → `_refresh_user_lending_snapshot`) | Either `_gross_profit_from_ledgers()` (ledgers per currency + tickers) or `_fetch_all_funding_trades()` + `_ticker_prices_from_trades()` | `KEY_LENDING` (120s TTL) | Fold, GET /stats/{id}/lending |
| **Funding trades** (GET /api/funding-trades) | `_fetch_all_funding_trades()` + tickers | **None** (no cache) | When frontend calls it (e.g. after fold returns gross but no trades) |
| **Bot stats** | Redis/DB only (no Bitfinex) | — | Fold, GET /bot-stats/{id} |

So the **same Bitfinex “bucket”** (wallets vs funding/lending) is not called twice in one backend request. But **ticker** and **funding-trades** can be used in ways that add extra work or duplicate calls.

---

## 2. Duplicate or combinable Bitfinex usage

### 2.1 Ticker prices (public API)

- **Wallets:** `_portfolio_allocation_snapshot` calls `_fetch_ticker_prices(currencies_for_ticker)` (currencies above ~$150).
- **Lending:** `_gross_profit_from_ledgers` or `_refresh_user_lending_snapshot` (trades path) also call `_fetch_ticker_prices` (or `_ticker_prices_from_trades` which may trigger ticker fetch).

In one **dashboard-fold**, `_wallets()` and `_lending()` run in **parallel**. If both go live (cache miss), **ticker prices can be fetched twice** (once for wallets, once for lending). There is a 60s in-memory `_ticker_cache` in `_fetch_ticker_prices`, so the second call may hit cache only if the **same symbol set** is used; wallet vs lending often use different currency sets, so you can still get **two ticker requests** per fold.

**Improvement:** In the fold handler, fetch ticker prices **once** for the union of currencies needed by wallets and lending, then pass that price map into both `_portfolio_allocation_snapshot` and `_refresh_user_lending_snapshot` (or their callees). That removes duplicate ticker calls on cold cache.

### 2.2 Funding trades: same data, two requests

- **Lending cache** explicitly **drops trades** before storing: `cache_data.pop("trades", None)`. So when fold returns lending from **cache or DB fallback**, the response has **no trades**.
- Frontend **ensureLendingTrades** runs when `gross_profit > 0` and `!data.trades || data.trades.length === 0`. It then calls **GET /api/funding-trades**.
- **GET /api/funding-trades** calls `_fetch_all_funding_trades()` again (same Bitfinex endpoint as lending).

So whenever the user gets **gross from cache/DB but no trades**, the app does:

1. Fold → lending with gross, no trades (from cache/DB).
2. Frontend → GET /api/funding-trades → **second Bitfinex funding-trades call**.

So the **same Bitfinex funding-trades API** is effectively used twice for the same user/session in that scenario.

**Improvement (choose one or combine):**

- **A) Fold returns trades when possible:** In `dashboard_fold`, when lending comes from **cache or DB** and has gross but no trades, **once per fold** call the same logic as `get_funding_trades` (or a shared helper), attach trades to the lending payload, and return them. Frontend then does **not** need to call `/api/funding-trades` for that load. No change to frontend except to stop calling `ensureLendingTrades` when the fold response already includes trades.
- **B) Cache trades in KEY_LENDING:** When we refresh lending from Bitfinex, store **trades** in the lending cache (and return them). Then fold can return cached lending **with** trades; frontend again avoids a second request. Trade-off: cache size and memory (list of trades per user).
- **C) Single “lending + trades” endpoint:** Replace “GET /stats/{id}/lending” and “GET /api/funding-trades” with one “GET /api/lending-with-trades” (or extend fold) that always returns gross + net + fee + trades when available. Frontend uses one call; backend can still use KEY_LENDING and optionally a separate trades cache if needed.

Recommendation: **A** or **B** so the frontend never needs a follow-up funding-trades request after fold.

---

## 3. Full request flow (what runs when)

### 3.1 Initial dashboard load (after login)

1. **Session / token:** NextAuth + optional bootstrap + GET /api/me.
2. **Prefetch:** One **GET /api/dashboard-fold** (already in place).
   - Backend runs in parallel: `_wallets()`, `_bot_stats()`, `_lending()`, then sync `_get_user_status_data`, `_get_token_balance_for_fold`, `_get_deduction_multiplier`.
   - If **wallets** cache miss → 3 Bitfinex auth calls + 1 ticker call.
   - If **lending** cache miss → ledgers or funding-trades + tickers.
   - If both miss → **2 ticker fetches** (see above) and **2 separate Bitfinex flows**.
3. **After fold:** If lending has `gross_profit > 0` and no `trades`, frontend calls **GET /api/funding-trades** → **extra HTTP request** and **duplicate Bitfinex funding-trades** (see 2.2).
4. **Referral:** Fetched only when user opens Referral/Settings (deferred), via **GET /api/v1/user/referral-bundle** (single request).

So the main cost is: **one fold** (which can trigger 2 Bitfinex flows + 2 ticker fetches) plus **one extra request + Bitfinex** when trades are missing.

### 3.2 What makes it feel slow

- **Cold caches:** First load or after TTL → both wallets and lending hit Bitfinex; plus ticker twice.
- **Second request:** ensureLendingTrades → /api/funding-trades adds latency and another Bitfinex call.
- **Waterfall:** Fold is one big request; until it finishes, the UI waits. No streaming or partial response.

---

## 4. Calculations that can stay or move to frontend (no backend data change)

These do **not** change stored data; they only affect display or derived state on the client.

| What | Where today | Note |
|------|-------------|------|
| **Chart series (7d/30d/90d)** | Frontend: `deriveChartHistoryFromTrades(trades, range)` in ProfitCenter | Already frontend; no change. |
| **Token usage % and “Used”** | Frontend: `used = total_tokens_added - tokens_remaining`, progress bar % | Already frontend; no change. |
| **Deduction multiplier display** | Frontend: “1 USD gross = X tokens” from context | Already frontend; no change. |
| **Formatting** | Frontend: dates, numbers, reason labels (e.g. `formatUsdtReason`) | Keep on frontend. |
| **Filtering / sorting** | Frontend: date range, tab filter, table sort | Keep on frontend. |
| **“Remaining” vs “Used”** | Frontend: from token_balance (remaining, added, deducted) | Already derived on frontend. |
| **Wallet “idle”** | Backend: `idle_usd = total_wallet_usd - credits_usd - offers_usd` | Could be moved to frontend if backend returned only total_wallet_usd, credits_usd, offers_usd; then frontend computes idle. Saves no Bitfinex calls; optional. |
| **Net = gross × (1 - 15%)** | Backend (and frontend for display) | Could be frontend-only if backend sent only gross; then frontend computes net and fee. Saves no Bitfinex; optional. |

So the **big wins** are not “move more math to frontend” but **fewer Bitfinex calls and fewer HTTP round-trips** (see sections 2 and 3).

---

## 5. Recommendations for 1000 traders

### 5.1 Backend (Bitfinex and fold)

1. **Single ticker fetch per fold**  
   In `dashboard_fold`, before or in parallel with wallets/lending, determine the **union** of currencies needed for both. Fetch ticker prices **once** for that set; pass the price map into both wallet and lending logic so neither path does its own ticker call. Reduces duplicate public ticker calls when both caches miss.

2. **Avoid duplicate funding-trades call**  
   When fold returns lending with **gross but no trades** (cache or DB), either:
   - **Option A:** Inside the same fold request, call the same funding-trades logic once and attach trades to the lending payload so the frontend does not call GET /api/funding-trades, or  
   - **Option B:** Store trades in KEY_LENDING (and return them from cache) so fold can return cached lending with trades.  
   Then remove or relax the frontend’s **ensureLendingTrades** for the “fold already has trades” case.

3. **Keep short TTL and invalidation**  
   Keep 90s/120s cache and invalidate after mutations so 1000 traders don’t hammer Bitfinex; the above changes only reduce **redundant** calls within one request or one session.

4. **Optional: Lending cache includes trades**  
   If you choose 2.B, cache trades in KEY_LENDING and return them from fold so one request gives full lending + trades and the UI doesn’t need a second request.

### 5.2 Frontend

1. **Don’t call /api/funding-trades when fold already has trades**  
   If the fold response’s lending object already has `trades` and `trades.length > 0`, **skip** `ensureLendingTrades` (no GET /api/funding-trades). Only call it when gross > 0 and trades are missing (until backend fills trades in fold as in 5.1.2).

2. **Already done**  
   - Single fold with token_balance.  
   - Referral bundle and deferred referral fetch.  
   - Token balance from fold in ProfitCenter/Settings.

3. **Optional: Show something before fold completes**  
   E.g. show layout/skeleton or cached data from sessionStorage immediately, then stream in fold result. Doesn’t reduce Bitfinex calls but can make the page feel faster.

### 5.3 Scale (1000 traders)

- **Backend:** One fold per dashboard load; fold runs wallets + lending in parallel and reuses one ticker fetch. No second request for trades when backend returns them in fold or from cache.
- **Bitfinex:** Per-user caches (KEY_WALLETS, KEY_LENDING) and 60s ticker cache spread load; duplicate calls within the same request/session are removed.
- **Frontend:** One HTTP request for initial data (fold); no extra request for trades when fold includes them.

---

## 6. Summary table

| Issue | Current | Improvement |
|-------|--------|-------------|
| Ticker prices | Fetched in both wallets and lending paths (2× when both live) | One shared ticker fetch per fold; pass into both paths |
| Funding trades | Fold often returns gross without trades → frontend calls /api/funding-trades → same Bitfinex again | Fold fills trades when from cache/DB, or cache stores trades; frontend skips second request when fold has trades |
| Lending cache | Trades not stored | Optionally store trades in KEY_LENDING and return from fold |
| ensureLendingTrades | Always calls /api/funding-trades when gross > 0 and no trades | Call only when fold response really has no trades (or remove once backend always returns trades) |

Implementing the **single ticker fetch** and **fold returning or caching trades** (plus frontend not requesting trades again when fold has them) will reduce Bitfinex calls and round-trips without changing any backend *data*; all display math can stay or move to frontend as above without affecting correctness.
