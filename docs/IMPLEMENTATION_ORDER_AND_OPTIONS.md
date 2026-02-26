# Implementation Order and Options

Refined workflow for Profit Center, credits, plans, Terminal, and 1000+ user scale.

---

## Recommended implementation order

1. **Data & definitions (done)**
   - **Gross Profit** = total USD earned from lending trade history since user registration, *before* Bitfinex fee.
   - **Net Earnings** = same history, *after* Bitfinex fee (15%), *before* platform charge.
   - **Server-side only**: Gross profit is stored in the backend (`user_profit_snapshot.gross_profit_usd`) and updated only by the server (on-demand refresh or daily cron). The frontend always reads from the API; the source of truth is the DB.
   - Both computed in `/stats/{user_id}/lending` and persisted to `user_profit_snapshot`.
   - **Token rule**: 1 USDT gross profit = 10 tokens used; stored in `user_token_balance` and recalculated from snapshot (no extra Bitfinex call).
   - **Daily update**: The API server runs the gross profit refresh **automatically at 09:40 UTC** every day (in-process scheduler; no cron or Task Scheduler needed). When you start the backend with `uvicorn main:app`, the job is scheduled. Optional: run `scripts/daily_refresh_gross_profit_0940utc.py` via cron only if the API is not running (e.g. separate cron host). Requests are spaced to respect Bitfinex API limits.

2. **Token balance storage and refresh**
   - When lending stats are computed, persist snapshot *and* update `user_token_balance` (tokens_remaining, last_gross_usd_used).
   - On login: read from snapshot (no Bitfinex call). Optionally if snapshot is older than 24h, trigger one fetch and then update snapshot + tokens.
   - Daily job: same as login—prefer snapshot; refresh from API only when stale to minimize API usage.

3. **Remove 7-day trial**
   - Free tier = 100 tokens, no time limit. Do not set `pro_expiry` on connect for trial users.
   - Keep `pro_expiry` only for paid subscriptions (set by Stripe webhook). UI shows token credit only, not "X days remaining."

4. **Plans (Pro / AI Ultra / Whales)**
   - **Pro** 20 USDT/mo: 1500 tokens, 30-min rebalancing, analytics, email, priority support.
   - **AI Ultra** 60 USDT/mo: 9000 tokens, 3-min rebalancing, analytics, email, Gemini AI, priority support.
   - **Whales AI** 200 USDT/mo: 40000 tokens, 1-min rebalancing, analytics, email, Gemini AI, priority support.
   - Stripe: create products and use env `STRIPE_PRICE_PRO_MONTHLY`, `STRIPE_PRICE_AI_ULTRA_MONTHLY`, `STRIPE_PRICE_WHALES_MONTHLY`.

5. **UI**
   - **Profit Center**: Labels "Gross Profit" and "Net Earnings" with short descriptions (since registration; before/after Bitfinex fee).
   - **Subscription**: Show plans and token credits; remove any "7-day trial" copy.
   - **Terminal**: Tab between Subscription and Settings. Visible to all; content (live terminal) only for Whales AI (or Whales + AI Ultra). Others see "Upgrade to Whales AI to see the live trading terminal."

6. **Scalable worker architecture (Phase 3)**
   - **Task queue**: Celery or Dramatiq + Redis. One "Dispatcher" enqueues jobs (e.g. `sync_user_wallets`, `run_lending_logic`).
   - **Stateless workers**: One job = load user keys, run *one* lending cycle (scan, deploy matrix, cancel stuck), write result, release. No long-lived `run_loop()` per user.
   - **Refactor bot**: `lending_worker_engine.run_one_lending_cycle()` runs one cycle per user (scan wallets, deploy matrix per asset, then return). Workers call it per job; Dispatcher re-enqueues the user after `rebalance_interval` minutes.
   - **IP / rate limits**: For 1000+ users, consider proxy rotation or multiple execution nodes so Bitfinex does not see all traffic from one IP.

7. **Whales terminal**
   - Workers stream log lines to Redis or DB; Terminal tab for Whales fetches or subscribes (SSE/WebSocket) to show live output.

---

## Options / uncertainties

| Topic | Options | Recommendation |
|-------|--------|-----------------|
| **Token balance refresh** | (a) On login: only read snapshot. (b) If snapshot &gt; 24h old, trigger one Bitfinex fetch and update snapshot + tokens. | (b) for accuracy with minimal API use. |
| **Stripe** | New products (Pro 20, AI Ultra 60, Whales 200) must be created in Stripe Dashboard; code references price IDs via env. | Set env after creating prices. |
| **Terminal visibility** | Only Whales vs Whales + AI Ultra. | Start with Whales only; extend to AI Ultra if needed. |
| **Bot refactor** | Current `bot_engine` has `run_loop()` with `while True`. Worker should run one cycle per job. | Add `lending_worker_engine.run_one_cycle()` that performs one tick; queue schedules next run by rebalance_interval. |
| **AI (Gemini) cost** | 1000 users × 1 request/hr = 24k requests/day. | Use "strategy grouping" (similar balances share same AI logic) to cut cost by ~90%. |

---

## Summary

- **Done**: Profit Center (Gross/Net from lending history), snapshot persistence, token credits (100/1500/9000/40000), plan config (30/3/1 min), no 7-day trial on connect, Terminal tab order (Subscription → Terminal → Settings).
- **To do**: Persist token balance when snapshot is updated; Terminal content gated by plan; stateless `run_one_cycle` for workers; optional log streaming for Whales terminal.
