# Bitfinex API Key Revenue Protection (utrader.io)

Prevents revenue loss when users remove or invalidate their Bitfinex API key (e.g. 05:00 UTC deletion / 11:00 UTC restoration).

## 1. Historical Ledger Cache (09:00 UTC)

- **Schedule**: Daily 09:00 UTC batch job.
- **Action**: For each user with stored API keys, fetch full Margin Funding ledger from Bitfinex and cache in Redis (encrypted, 7-day TTL).
- **Validation**: If the API key is invalid during this fetch, an in-app/email alert is sent: *"Your Bitfinex API key is invalid – update by 10:00 UTC to avoid fee processing with cached data."*
- **Log**: `"09:00 UTC: Cached ledger data for {email} (API key valid)"`.
- **Storage**: `services/ledger_cache.py` – encrypted payload (entries + `start_ms`) in Redis key `ledger_cache:v1:{user_id}:{date}`.

## 2. API Key Lock (09:55–10:35 UTC)

- **Window**: 09:55–10:35 UTC (critical fee calculation).
- **UI**: "Delete API Key" / "Unlink Account" is greyed out with tooltip: *"API key changes disabled during daily fee calculation (10:00–10:30 UTC)"*.
- **Backend**: `DELETE /api/keys` and `POST /api/keys` (overwrite) return **403 Forbidden** with: *"API key modification disabled during daily fee processing (09:55–10:35 UTC)."*
- **Lock status**: `GET /api/keys` returns `api_key_modification_locked: true` during the window so the frontend can disable the button.
- **If key is deleted via Bitfinex directly**: 10:30 deduction falls back to 09:00 cached data (see below).

## 3. 10:30 UTC Deduction (Fallback to Cache)

- If the 10:00 UTC API fetch failed for a user (invalid/deleted key), `_apply_09_00_cache_before_deduction` runs before the normal deduction.
- It loads 09:00 cached ledger for that user/date and computes `daily_gross_profit_usd` from the cache, then updates `user_profit_snapshot`.
- Deduction then runs as usual using the stored snapshot (no skip).
- **Log**: `"10:30 UTC: Processed deduction for {email} using 09:00 UTC cached data (API key invalid/deleted)"`.
- **User notification**: Optional – *"Your daily fee was processed using cached data (no changes needed – reconciliation will run on key restoration)."*

## 4. 11:15 UTC Catch-Up Deduction

- **Schedule**: Daily 11:15 UTC.
- **Eligible users**: Snapshot has `daily_gross_profit_usd = 0` and vault exists with `keys_updated_at` ≥ 10:30 UTC today (key restored after 10:30).
- **Action**: For each such user, call `_daily_10_00_fetch_and_save` (re-fetch with restored key), then run `run_daily_token_deduction` so the catch-up is applied.
- **Log**: `"11:15 UTC: Catch-up deduction for {email} (API key restored – deducted using fresh ledger)"`.
- **Late fee (future)**: After 3 days of invalid key with no restoration, a 5% late fee can be applied (constants: `LATE_FEE_DAYS`, `LATE_FEE_PCT`). Admin alert for ≥2 key deletions per month can be added via audit log.

## 5. Automated Tests

In `tests/test_comprehensive_deduction_plan.py`:

- `test_api_key_lock_0955_1035`: Lock window true during 09:55–10:35, false outside.
- `test_cached_data_deduction_0500_deletion`: Daily gross from cache-derived entries (e.g. 3.271661).
- `test_catchup_deduction_1100_restoration`: 11:15 constants and next-run wait.
- `test_late_fee_after_3_days`: `LATE_FEE_DAYS=3`, `LATE_FEE_PCT=0.05`, example 3.435244.

Tests skip gracefully if `freezegun` or `pytest` are missing.

## 6. Logging & Alerts

- API key lock triggers: logged when DELETE/POST blocked (user_id).
- Cached data usage: logged at 10:30 for user/email.
- Catch-up deductions: logged at 11:15 with user/email.
- Late fee: to be logged when applied (after 3-day logic is implemented).
- Admin alerts: `_alert_admins_deduction_failure` for invalid key at 09:00, cache failures, and (optional) repeated key deletion ≥2×/month.

## Backward Compatibility

- Existing 10:00 / 10:30 deduction logic unchanged; cache is a fallback when 10:00 fetch failed.
- No new required DB migrations for basic flow; optional columns (e.g. `last_deduction_status`) can be added later for richer status.
