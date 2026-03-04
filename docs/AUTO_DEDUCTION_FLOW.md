# How Auto Deduction Works: From API Call to Deduction

This document traces the full path from the scheduler and Bitfinex API calls through to the actual token deduction and persistence.

---

## 1. Overview: Two Schedulers Feed One Deduction

Auto deduction depends on **two separate async tasks** that run at different UTC times:

| Time (UTC) | Task | Role |
|------------|------|------|
| **09:00** | `_run_09_00_ledger_cache_scheduler` | Cache Margin Funding ledgers in Redis (fallback if 10:00 fails or key deleted). |
| **10:00** | `_run_daily_gross_profit_scheduler` | Call Bitfinex per user → write `user_profit_snapshot` (gross + daily_gross). Optional 10:10 retry if data incomplete. |
| **10:30** | `_run_daily_token_deduction_scheduler` | Final fetch for users still with no daily_gross → 09:00 cache fill → **run deduction** (no Bitfinex in deduction itself). |

They are started in `main.py` on lifespan (around L1052–1056):

```python
ledger_cache_task = asyncio.create_task(_run_09_00_ledger_cache_scheduler())
scheduler_task = asyncio.create_task(_run_daily_gross_profit_scheduler())
deduction_task = asyncio.create_task(_run_daily_token_deduction_scheduler())
```

The **10:30 task** is what ultimately runs the deduction; it may call the Bitfinex API only for users who still have no `daily_gross_profit_usd` (final fetch).

---

## 2. When 10:30 Fires: Deduction Scheduler Entry Point

**File:** `main.py`  
**Function:** `_run_daily_token_deduction_scheduler` (L652–744)

**Flow:**

1. **Wait until 10:30 UTC**
   - `wait_sec = _get_next_1030_utc_wait_sec()` → `_get_next_utc_wait_sec(10, 30)` (L198–204).
   - Computes seconds until next 10:30 UTC; sleeps that long.

2. **Retry loop** (up to `DEDUCTION_MAX_RETRIES`, default 3, 5 min apart if failed).

3. **Step A – Final fetch (Bitfinex API)**  
   For users who still have `daily_gross_profit_usd` 0 or None:
   - Get all user IDs with vault.
   - For each such user, call `_daily_10_00_fetch_and_save(uid, db_u, accept_fresh_data=True)` (L694).
   - `accept_fresh_data=True` skips the “latest entry &lt; 20 mins” check so late Bitfinex data can be saved.

4. **Step B – 09:00 cache fill**
   - `await _apply_09_00_cache_before_deduction(db, redis)` (L703).
   - For users still with `daily_gross_profit_usd == 0` or `None`, fills snapshot from 09:00 cached ledger (or DB fallback if Redis down).

5. **Step C – Expire session**
   - `db.expire_all()` (L707) so the next read sees the latest snapshot (including final fetch / cache updates).

6. **Step D – Run deduction**
   - `log_entries, err = run_daily_token_deduction(db)` (L708).
   - If `err`, retry after `DEDUCTION_RETRY_INTERVAL_SEC`; else append to in-memory `_deduction_logs` and break.

7. **On final failure**
   - Alert admins via `_alert_admins_deduction_failure`.

---

## 3. Bitfinex API Call Path (Final Fetch / 10:00 Style)

**File:** `main.py`  
**Function:** `_daily_10_00_fetch_and_save(user_id, db, accept_fresh_data=False)` (L3488–3567)

This is the only place that **calls Bitfinex** to refresh gross profit and daily gross for deduction.

**Steps:**

1. Load user and vault; get API keys → `BitfinexManager(bfx_key, bfx_secret)`.
2. **Ledger fetch:**  
   `entries, latest_mts, fetch_err = await _fetch_all_margin_funding_entries(mgr, currencies=ledger_currencies)` (L3515).
   - **Under the hood:** `_fetch_all_margin_funding_entries` (L3455) loops over currencies and calls `_fetch_ledgers_script_style(mgr, currency, limit=100)` (L3471).
   - **Actual API:** `_fetch_ledgers_script_style` (L3433) calls `mgr.ledgers_hist(currency=currency, limit=limit)` (L3439) → Bitfinex **`/v2/auth/r/ledgers/{currency}/hist`** (Margin Funding ledger).
3. **Completeness (only when `accept_fresh_data=False`):**  
   `_is_ledger_data_complete(latest_mts)` (L3518): latest entry must be at least `LEDGER_FRESHNESS_MINUTES` (20) old.
4. **Convert to USD:**  
   `_gross_and_fees_from_ledger_entries(entries, start_ms=..., end_ms=..., usd_prices=...)` for:
   - full period → `gross`, `fees`;
   - **today UTC** (`start_today_ms`–`end_today_ms`) → `daily_gross`.
5. **Write to DB:**  
   Update or create `user_profit_snapshot`:  
   `gross_profit_usd`, `net_profit_usd`, `bitfinex_fee_usd`, `daily_gross_profit_usd`, `last_daily_snapshot_date` (= today), `updated_at`.  
   Detect vault/account switch and set `account_switch_note` if needed.
6. **Return:** `(True, False, None)` on success; `(False, True, None)` if incomplete and not accepted; `(False, False, err)` on API error.

So: **“API calling”** in auto deduction = this single path, used both by the **10:00 scheduler** (with `accept_fresh_data=False`) and by the **10:30 final fetch** (with `accept_fresh_data=True`).

---

## 4. 09:00 Cache Fill (When 10:00 / Final Fetch Left daily_gross Empty)

**File:** `main.py`  
**Function:** `_apply_09_00_cache_before_deduction(db, redis)` (L583–648)

- **Input:** All users with token balance + profit snapshot where `daily_gross_profit_usd` is 0 or None.
- **Data source:** `ledger_cache_svc.get_ledger_cache_with_fallback(redis, db, user_id, today_utc)` (from 09:00 cache or DB fallback).
- **Logic:** From cached ledger entries, compute `daily_gross` for **today UTC** via `_gross_and_fees_from_ledger_entries(..., start_today_ms, end_today_ms, ...)` and write to `user_profit_snapshot.daily_gross_profit_usd` (and related fields). If Redis is down, use DB `last_cached_daily_gross_usd`.
- **Effect:** Those users get a non-zero `daily_gross_profit_usd` so the deduction step can run without calling Bitfinex again.

---

## 5. Deduction Procedure (Core)

**File:** `services/daily_token_deduction.py`  
**Function:** `run_daily_token_deduction(db, user_ids=None)` (L122–223)

**Input:**  
- `db`: SQLAlchemy session.  
- `user_ids`: optional; if provided (e.g. 11:15 catch-up), only those users are processed; otherwise all with token balance + snapshot.

**Per user:**

1. **Skip if already processed today**  
   `if last_deduction_processed_date == date_utc` (today UTC) → skip (no double charge).

2. **Read snapshot**  
   `daily_gross = snap.daily_gross_profit_usd` (rounded to 2 decimals). If None → 0.

3. **Rule:**  
   `apply_deduction_rule(tokens_before, daily_gross)` (L33–42):
   - If `daily_gross <= 0` → no deduction.
   - Else `new_tokens = max(0, tokens_before - daily_gross)` (1:1 USD = tokens deducted).

4. **Referral:**  
   Compute `purchased_burned` from `purchased_tokens` and free balance; if &gt; 0, call `apply_referral_rewards(db, user_id, purchased_burned)`.

5. **Apply deduction in DB**  
   `token_ledger_svc.deduct_tokens(db, user_id, tokens_deducted)` (L174).

6. **Update snapshot and balance row**  
   - `token_row.last_gross_usd_used = daily_gross`  
   - `token_row.updated_at = now_utc`  
   - `snap.deduction_processed = True`  
   - `snap.last_deduction_processed_date = date_utc`  
   - Clear `snap.account_switch_note` if set.

7. **Log and persist**  
   - Append to in-memory `log_entries` (dict with user_id, gross_profit, tokens_deducted, tokens_remaining_after, timestamp, etc.).
   - If `DeductionLog` model exists: `db.add(DeductionLog(...))` with same data (L196–205).
   - After all users: `db.commit()`.

**Return:** `(log_entries, None)` on success; `(log_entries, str(e))` on exception (after rollback).

---

## 6. Actual Balance Update (Token Ledger Service)

**File:** `services/token_ledger_service.py`  
**Function:** `deduct_tokens(db, user_id, amount)` (L115–136)

- **Input:** `amount` = tokens to deduct (rounded to 2 decimals).
- **SQL:**
  ```sql
  UPDATE user_token_balance
  SET tokens_remaining = GREATEST(0, tokens_remaining - :amt),
      updated_at = NOW()
  WHERE user_id = :uid
  ```
- **Return:** New `tokens_remaining` (from `get_tokens_remaining`).

No Bitfinex call here; it only updates `user_token_balance`.

---

## 7. End-to-End Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  LIFESPAN START (main.py)                                                    │
│  asyncio.create_task(_run_09_00_ledger_cache_scheduler())                    │
│  asyncio.create_task(_run_daily_gross_profit_scheduler())   ← 10:00 fetch    │
│  asyncio.create_task(_run_daily_token_deduction_scheduler()) ← 10:30 deduct  │
└─────────────────────────────────────────────────────────────────────────────┘

09:00 UTC   _run_09_00_ledger_cache_scheduler
           → Bitfinex /auth/r/ledgers/{currency}/hist per user
           → Redis cache (7-day TTL) for fallback at 10:30

10:00 UTC   _run_daily_gross_profit_scheduler
           → For each user: _daily_10_00_fetch_and_save(uid, db)
                → _fetch_all_margin_funding_entries(mgr)  ← Bitfinex ledgers
                → _gross_and_fees_from_ledger_entries (today UTC) → daily_gross
                → Write user_profit_snapshot (gross_profit_usd, daily_gross_profit_usd, last_daily_snapshot_date)
           → 10:10 retry for incomplete users (optional)

10:30 UTC   _run_daily_token_deduction_scheduler
           │
           ├─ 1) Final fetch: for users with daily_gross 0/None
           │      _daily_10_00_fetch_and_save(uid, db_u, accept_fresh_data=True)
           │      (same Bitfinex path as 10:00)
           │
           ├─ 2) _apply_09_00_cache_before_deduction(db, redis)
           │      Fill snapshot from 09:00 cache for users still 0/None
           │
           ├─ 3) db.expire_all()
           │
           └─ 4) run_daily_token_deduction(db)
                  │
                  ├─ For each user (snapshot.daily_gross_profit_usd):
                  │   apply_deduction_rule(tokens_before, daily_gross)
                  │   → token_ledger_svc.deduct_tokens(db, user_id, tokens_deducted)
                  │   → UPDATE user_token_balance SET tokens_remaining = ...
                  │   → DeductionLog row + snapshot flags (last_deduction_processed_date, etc.)
                  │
                  └─ db.commit()
```

---

## 8. Summary Table

| Step | Location | What runs | Bitfinex? |
|------|----------|-----------|-----------|
| Schedule 10:30 | `main.py` L657–661 | Sleep until next 10:30 UTC | No |
| Final fetch | `main.py` L667–698 | `_daily_10_00_fetch_and_save(uid, accept_fresh_data=True)` for users with no daily_gross | Yes (ledgers/hist) |
| Cache fill | `main.py` L701–704 | `_apply_09_00_cache_before_deduction` | No (uses Redis/DB cache) |
| Expire | `main.py` L707 | `db.expire_all()` | No |
| Deduction | `main.py` L708 → `services/daily_token_deduction.py` L122 | `run_daily_token_deduction(db)` | No |
| Balance update | `services/token_ledger_service.py` L115 | `deduct_tokens(db, user_id, amount)` → UPDATE user_token_balance | No |
| Persist log | `services/daily_token_deduction.py` L195–205 | `DeductionLog` row + in-memory `_deduction_logs` | No |

So: **API calling** is only in the 10:00 scheduler and in the 10:30 **final fetch**; the **deduction procedure** itself only reads from `user_profit_snapshot` and updates `user_token_balance` and `deduction_log`.
