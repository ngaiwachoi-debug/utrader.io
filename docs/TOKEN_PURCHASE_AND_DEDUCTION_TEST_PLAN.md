# Token purchase and deduction – full testing plan (uid 2)

## Overview

1. **Subscription (Whales AI, bypass Stripe):** User 2 subscribes to Whales monthly (200 USD) with payment bypass; verify 40,000 tokens added and entry in token add log.
2. **Rollback two days:** Remove auto/manual deduction records for user 2 for yesterday and today (rollback tokens, clear `last_deduction_processed_date`).
3. **Test auto deduction:** Set snapshot so today’s daily gross = 4.41; run daily deduction; verify balance and `last_gross_usd_used` ≈ 4.41.
4. **Rollback again, test manual trigger:** Set snapshot for yesterday = 26.83 and today = 4.41; run manual trigger; verify two deductions (26.83, 4.41) and `last_gross_usd_used` ≈ 4.41.
5. **Final rollback:** Remove today’s and yesterday’s deduction records once more.

---

## Prerequisites

- Backend: `ALLOW_DEV_CONNECT=1` for subscription bypass and dev login (`/dev/login-as`).
- DB: `user_profit_snapshot` and `user_token_balance` exist for user 2.
- Rollback/deduction tests use DB directly (no admin JWT); subscription test needs backend running with `ALLOW_DEV_CONNECT=1`.

---

## 1. Subscription (Whales, bypass) – purchase amount 200 USD, 40,000 tokens

**Steps:**

1. Log in as user 2 (dashboard).
2. Go to Subscription; enable “Bypass payment (dev)”.
3. Choose Whales AI, Monthly (200 USD).
4. Click Subscribe. Backend should call `POST /api/v1/subscription/bypass` and apply plan + 40,000 tokens.

**Checks:**

- **Purchase amount:** Plan is Whales monthly = 200 USD (no real charge).
- **Token balance:** `GET /api/v1/users/me/token-balance` (as user 2): `tokens_remaining` increased by 40,000; `total_tokens_added` includes the new 40,000.
- **Token add log (admin):** Admin → Token add log; filter by user_id 2; one row: reason `subscription_monthly`, amount 40000.
- **Token add log (user):** User 2 → Settings → “Token added history”; one row: Subscription, 40000.

**API (script):** Obtain JWT for user 2 (e.g. dev connect by email), then:

- `POST /api/v1/subscription/bypass` with `{ "plan": "whales", "interval": "monthly" }`.
- `GET /api/v1/users/me/token-balance` → assert +40,000.
- Admin: `GET /admin/token-add/logs?user_id=2` → assert one entry subscription_monthly 40000.

---

## 2. Remove previous two days (auto and manual) deduction records

**Goal:** So we can re-run deduction for “yesterday” and “today” with known amounts.

**Steps (admin or script):**

1. **Rollback user 2 for today (YYYY-MM-DD):**
   - `POST /admin/deduction/rollback/2/{today}` (admin JWT).
   - Or: delete from `deduction_log` where `user_id=2` and `timestamp_utc` on today; add back `tokens_deducted` to balance; set `user_profit_snapshot.last_deduction_processed_date = NULL` for user 2.

2. **Rollback user 2 for yesterday:**
   - `POST /admin/deduction/rollback/2/{yesterday}`.

3. **Clear last_deduction_processed_date** for user 2 so the next run can deduct again:
   - `UPDATE user_profit_snapshot SET last_deduction_processed_date = NULL WHERE user_id = 2`.

Script: `scripts/rollback_uid2_two_days.py` (see below).

---

## 3. Test auto deduction (today only, 4.41)

**Setup:**

- User 2’s `user_profit_snapshot`: `daily_gross_profit_usd = 4.41`, `last_daily_snapshot_date = today`, `last_deduction_processed_date = NULL`.
- No deduction record for today for user 2 (already rolled back).

**Run:**

- Trigger daily deduction (scheduler at 10:30 UTC, or run `run_daily_token_deduction(db)` in a script for user_ids=[2]).

**Verify:**

- `user_token_balance`: `tokens_remaining` decreased by 4.41; `last_gross_usd_used = 4.41`.
- `deduction_log`: one row for user 2, date today, `tokens_deducted = 4.41`.
- Admin → Deduction logs: one entry for user 2, Deducted 4.41.

---

## 4. Remove records again; test manual trigger (yesterday 26.83 + today 4.41)

**Rollback:**

- Rollback user 2 for today again (so today’s 4.41 is reverted).

**Setup for “yesterday” first:**

- `user_profit_snapshot` for user 2: `daily_gross_profit_usd = 26.83`, `last_daily_snapshot_date = yesterday`, `last_deduction_processed_date = NULL`.
- Run manual trigger with **refresh_first=False** so snapshot is not overwritten:
  - Backfill step will see `last_deduction_processed_date < last_daily_snapshot_date` and call `run_deduction_for_user_for_date(db, 2, yesterday, 26.83)`.
- After backfill: `last_deduction_processed_date = yesterday` for user 2.

**Setup for “today” then:**

- Set `daily_gross_profit_usd = 4.41`, `last_daily_snapshot_date = today`, `last_deduction_processed_date = NULL` (so today is not skipped).
- Run `run_daily_token_deduction(db)` again (or manual trigger with refresh_first=False): deducts 4.41 for today.

**Verify:**

- `deduction_log`: two rows for user 2 — one yesterday 26.83, one today 4.41.
- `user_token_balance`: `tokens_remaining` decreased by 26.83 + 4.41; `last_gross_usd_used = 4.41`.
- Admin deduction logs: two entries, amounts 26.83 and 4.41.

---

## 5. Remove records once more

- Rollback user 2 for today and yesterday again (same as step 2).
- Leaves user 2 with no deduction records for those two days and `last_deduction_processed_date` cleared for a clean state.

---

## Scripts (run from project root)

| Script | Purpose |
|--------|--------|
| `python scripts/rollback_uid2_two_days.py` | Rollback user 2 for today and yesterday; clear `last_deduction_processed_date`. Run before auto/manual tests. |
| `python scripts/test_token_subscription_and_deduction_uid2.py` | **Requires backend running and ALLOW_DEV_CONNECT=1.** Gets JWT via `POST /dev/login-as`, calls `POST /api/v1/subscription/bypass` (whales monthly), checks balance and token_ledger for subscription_monthly 40000. |
| `python scripts/run_auto_deduction_test_uid2.py` | After rollback: set snapshot daily_gross=4.41 (today), run `run_daily_token_deduction` for user 2; assert one deduction 4.41 and `last_gross_usd_used` ≈ 4.41. |
| `python scripts/run_manual_trigger_test_uid2.py` | After rollback: backfill yesterday 26.83, then run deduction for today 4.41; assert two deductions and `last_gross_usd_used` ≈ 4.41; then rollback both days again. |

---

## Summary table

| Phase | Action | Expected |
|-------|--------|----------|
| 1 | Subscribe Whales monthly (bypass) as uid 2 | 200 USD plan; +40,000 tokens; token add log shows subscription_monthly 40000 |
| 2 | Rollback uid 2 for yesterday and today | No deduction rows for those days; tokens restored; last_deduction_processed_date cleared |
| 3 | Set daily_gross=4.41 (today), run auto deduction | One deduction 4.41; last_gross_usd_used ≈ 4.41 |
| 4 | Rollback today; set 26.83 yesterday, run manual (no refresh); then 4.41 today, run deduction | Two deductions 26.83 and 4.41; last_gross_usd_used ≈ 4.41 |
| 5 | Rollback yesterday and today again | Clean state |
