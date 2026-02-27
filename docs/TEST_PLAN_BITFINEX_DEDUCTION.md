# Comprehensive Test Plan: Bitfinex API, Token Deduction & Gross Profit

## Pre-Test Setup

1. **Staging**: Use a staging server with updated code (10:00 UTC single API call, 10:30 UTC deduction).
2. **Test user**: `choiwangai@gmail.com` (linked to a single test Bitfinex API key).
3. **Pre-load reference data** (Margin Funding Payment):
   - 2026-02-23: 2.181577 USD  
   - 2026-02-24: 24.080038 USD  
   - 2026-02-25: 36.190726 USD  
   - 2026-02-26: 6.477932 USD  
   - 2026-02-27: 3.271661 USD  
   - **Total: 72.201934 USD**
4. **Tools**: API client (Postman/curl), log viewer, DB viewer, time simulation (e.g. `freezegun` in Python).

---

## Scenario 1: Basic Flow (Normal Operation)

| Step | Simulated time | Action | Expected |
|------|----------------|--------|----------|
| 1 | 09:59 UTC | Verify no Bitfinex API calls for test user | Logs show 0 daily-fetch API calls (scheduler next run is 10:00). |
| 2 | 10:00 UTC | Trigger daily API fetch | 1 API call; full ledger stored; `gross_profit_usd` = 72.20 in `user_profit_snapshot`; `daily_gross_profit_usd` = 3.271661 (2026-02-27). |
| 3 | 10:29 UTC | Check deduction | No deduction run (next deduction at 10:30). |
| 4 | 10:30 UTC | Trigger daily deduction | No new API call (1 total for day); daily tokens deducted = 3.271661 (1:1); `used_tokens` = 722 (72.20×10); token balance reduced by 3.271661. |

**Automated**: `test_next_run_10_00_utc`, `test_next_deduction_10_30_utc`, `test_scenario1_used_tokens_722_not_739`, `test_scenario1_deduction_1_to_1_daily_gross`, `test_scenario1_09_59_no_fetch_before_10_00`.

---

## Scenario 2: Late/Incomplete Bitfinex Data (Safety Buffer)

| Step | Simulated time | Action | Expected |
|------|----------------|--------|----------|
| 1 | 10:00 UTC | Return partial API (4/5 entries; missing 2026-02-27) | Fetch marked incomplete (e.g. latest entry &lt; 20 min old); retry scheduled at 10:10 (2nd call). |
| 2 | 10:10 UTC | Return full API (all 5 entries) | Full data stored; `gross_profit_usd` = 72.20; no further retries. |
| 3 | 10:30 UTC | Run deduction | Uses complete data: daily tokens = 3.271661, used_tokens = 722. |
| 4 | (repeat) | 10:00 partial + 10:10 still partial | Deduction skipped for the day; admin alert logged; token balance unchanged. |

**Automated**: `test_scenario2_incomplete_when_latest_less_than_20_mins_old`, `test_scenario2_complete_when_latest_at_least_20_mins_old`.

---

## Scenario 3: Bitfinex Account Switch (Edge Case)

| Step | Simulated time | Action | Expected |
|------|----------------|--------|----------|
| 1 | Pre-10:00 | Account switch (unlink/re-link or mark “new account” in DB) | System flags switch (e.g. `keys_updated_at` &gt; `last_vault_updated_at`). |
| 2 | 10:00 UTC | Run daily API fetch | 1 API call; **new** account ledger stored (mock: 2 entries = 10.50 USD); `gross_profit_usd` = 10.50 (no carryover from old 72.20); `account_switch_note` set. |
| 3 | 10:30 UTC | Run deduction | Uses **only** new account data; daily tokens = new account daily gross; used_tokens = 10.50 × 10 = **105** (not 722). |

**Automated** (`tests/test_comprehensive_deduction_plan.py`):

- **test_scenario3_account_switch_pre_10_00_triggers_fresh_api_call**  
  Mocks: `mock_user` (id=1, vault `get_keys`/`created_at`), `mock_snap` (old `gross_profit_usd`=72.20, `last_vault_updated_at`=2026-02-26), `mock_vault` (`keys_updated_at`=2026-02-27 10:00 → triggers switch). Patch `_fetch_all_margin_funding_entries` → 2 entries (4.20 + 6.30 = 10.50 USD), `latest_mts` ≥25 mins old. Freezegun: 2026-02-27 10:00:00 UTC. Asserts: `_daily_10_00_fetch_and_save(1, mock_db)` returns `(True, False, None)`; snapshot `gross_profit_usd`=10.50; `account_switch_note` contains "Bitfinex account switched". **Fallback** (no freezegun/pytest/mock): `skip_scenario3()` → assert 10.50 × 10 = 105 tokens (no 722).

- **test_scenario3_deduction_uses_new_account_data_only**  
  Asserts: `used_tokens = int(10.50 * TOKENS_PER_USDT_GROSS) = 105` (not 722); `apply_deduction_rule(500, 1.05)` reduces by 1.05. Optional freezegun 10:30 UTC. **Fallback**: same constant checks.

**Helpers**: `mock_ledger_entries_new_account_10_50()`, `skip_scenario3(_e)`.

---

## Scenario 4: Duplicate API Call Prevention (Optional)

| Step | Simulated time | Action | Expected |
|------|----------------|--------|----------|
| 1 | 10:05 UTC | Manually trigger daily API fetch again | If implemented: blocked (e.g. “duplicate API call blocked — 1 call already made today”). |
| 2 | Restart at 10:10, re-trigger | If implemented: no new call (today’s API flag in DB). |

**Note**: Current code does not block a second manual trigger; scheduler runs only at 10:00 (and 10:10 retry for incomplete users). Blocking a second manual run would require a “daily API call count” or “last fetch time” guard. **Automated**: `test_scenario4_block_message_format` (message format only).

---

## Scenario 5: Calculation Precision (Decimal Accuracy)

| Step | Data | Expected |
|------|------|----------|
| 1 | Add entry 2026-02-28: 0.000001 USD; full sum = 72.201935 | `gross_profit_usd` = 72.20 (rounded to 2 decimals); used_tokens = 722 (72.20×10); full precision can be stored in DB for audit. |
| 2 | 10:30 deduction for 2026-02-28 | daily tokens deducted = 0.000001; token balance reduced by 0.000001. |

**Automated**: `test_scenario5_full_sum_72_201935_rounds_to_72_20`, `test_scenario5_daily_2026_02_27_is_3_271661`, `test_scenario5_daily_2026_02_28_tiny_entry`.

---

## Free Rider Prevention (API Key Removal/Loss During Fee Charging)

Validates revenue protection when the user removes or loses their Bitfinex API key (e.g. 05:00 UTC deletion, 11:00 UTC restoration).

| Step | Simulated time | Action | Expected |
|------|----------------|--------|----------|
| 1 | 05:00 UTC | Key deleted (mock) | User no longer has valid key. |
| 2 | 09:00 UTC | Pre-window cache run | Valid ledger data from 09:00 saved (log: "Cached ledger data for choiwangai@gmail.com"). |
| 3 | 10:00 UTC | API fetch | Fails (invalid key) → 10:30 will use 09:00 cached data. |
| 4 | 10:30 UTC | Deduction | Uses 09:00 cached data → 3.271661 tokens deducted; status = completed_cached (no skip). |
| 5 | 11:00 UTC | Key restored (mock) | User re-adds key. |
| 6 | 11:15 UTC | Catch-up deduction | Reconcile cached vs real-time; completed_catchup; no double-charge. |
| 7 | (3 days invalid) | No restoration | Day 4: 5% late fee (3.271661 × 1.05 = 3.435244); user alert. |

**Automated** (`tests/test_comprehensive_deduction_plan.py`):

- **test_free_rider_0500_key_deletion_1100_restoration**  
  Mocks: key deletion at 05:00, restore at 11:00; 10:00 fetch fails, 10:30 uses cache. Asserts: 09:00 cache saved; 10:30 completed_cached; 11:15 completed_catchup; total deducted 3.271661; no free ride. **Fallback**: constant checks (deduction 3.271661, `apply_deduction_rule`).

- **test_free_rider_api_key_lock_0955_1035**  
  Freezegun 10:00 UTC (within lock). Asserts: DELETE /api/keys returns 403 ("API key modification disabled during daily fee processing (09:55–10:35 UTC)"); UI Delete button greyed out; key deleted via Bitfinex directly → 10:30 uses 09:00 cached data. **Fallback**: lock constants and message format.

- **test_free_rider_late_fee_after_3_days**  
  Mock invalid key 3 days, no restoration. Asserts: Day 1 cached deduction 3.271661; Day 2–3 retry/fail/alert; Day 4 late fee 3.435244; user alert "update your API key to avoid 5% late fee". **Fallback**: `LATE_FEE_DAYS`, `LATE_FEE_PCT`, 3.435244.

- **test_free_rider_no_double_charge**  
  10:30 sets `deduction_processed=True`; 11:15 catch-up skips (log "already processed"), balance unchanged. **Fallback**: `_free_rider_fallback_double_charge()` (validates `deduction_processed` helpers).

- **test_free_rider_cached_fresh_reconciliation**  
  Cached daily_gross = 3.271661, fresh = 3.30 → difference 0.028339 deducted; log "Reconciliation: Charged extra 0.028339 tokens (undercharged)". **Fallback**: `_free_rider_fallback_reconciliation()` (3.30 - 3.271661 = 0.028339).

- **test_free_rider_late_fee_execution**  
  User `invalid_key_days=3`, 12:00 UTC run → late fee 3.435244 deducted, alert "5% late fee applied". **Fallback**: `_free_rider_fallback_late_fee_execution()`.

- **test_free_rider_repeated_deletion_alert**  
  User deletes key 2× in month → admin alert "Repeated API Key Deletion", `key_deletions["YYYY-MM"]` = 2. **Fallback**: `_free_rider_fallback_deletion_alert()`.

- **test_free_rider_redis_fallback**  
  RedisError on cache fetch → `get_ledger_cache_with_fallback` returns None (no crash). **Fallback**: validate `get_ledger_cache_with_fallback` and `CACHE_MAX_AGE_MINS`.

- **test_cache_freshness**  
  Cache age > 60 mins (e.g. 09:00 cache from 08:00) → rejected, log "Stale cache – skipping". **Fallback**: `cache_age_mins > 60` → rejected.

**Targeted fallbacks**: `_free_rider_fallback_lock()`, `_free_rider_fallback_late_fee()`, `_free_rider_fallback_catchup()` (split from generic constant checks).

**Negative edge cases**:
- Key restored after 11:15 UTC → catch-up window closed; next day’s 10:00/10:30 will use fresh data.
- Stale cache (>60 mins) → cache usage skipped; deduction uses 10:00 fetch only (or skips if key invalid).
- Lock window: 09:54 UTC = allowed (delete/modify); 09:55 UTC = blocked (403).
- **Incremental late fees**: invalid_key_days not reset after fee; day 3 = 5%%, day 4 = 10%%, day 5 = 15%%; **capped at 25%%** (MAX_LATE_FEE_PCT); day 7+ = 25%%. Log: "User {user_id} – late fee capped at 25%% (invalid_key_days={N})".
- **Post-11:15 key restore**: 23:00 UTC reconciliation sweep; **dry run first** (no DB write); only apply if dry run passes (e.g. no negative balance); admin alert "23:00 reconciliation dry run failed for user {user_id} – manual review needed" on failure. **Batching**: 10 users per batch, 1s delay between batches; log "23:00 reconciliation – batch {batch_num}/{total_batches} processed ({count} users)". reconciliation_completed set True after apply.
- **Key deletions JSON**: Malformed `key_deletions` in DB → `json.loads` wrapped in try/except; on JSONDecodeError reset to `{}`, log error, continue (no crash); admin alert count check still works.
- **Redis down**: DB cache (last_cached_daily_gross_usd) used for 10:30 deduction.
- **Trace ID**: All deduction/cache/late fee/reconciliation logs include trace_id (UUID format).

**New tests**: test_free_rider_incremental_late_fees, test_free_rider_key_restored_post_1115, test_free_rider_persistent_key_deletions, test_free_rider_redis_fallback_db_cache, test_free_rider_timezone_independence, test_trace_id_logging (see test file for fallback helpers). **Coverage**: late fee cap (25%%), 23:00 dry run + batching, key_deletions JSON validation.

---

## Post-Test Validation

1. **API call count**: Max 2 calls/day per user (10:00 + optional 10:10 retry).
2. **Timing**: No API calls before 10:00 UTC; no deductions before 10:30 UTC.
3. **Calculations**: `choiwangai@gmail.com` — Gross Profit = 72.20 USD, Used Tokens = 722 (never 739); daily deduction 1:1 with daily gross profit.
4. **Edge cases**: Account switch triggers fresh 10:00-style API usage; incomplete data skips deduction and alerts; duplicate-call blocking is optional.

---

## Running the Tests

- **Time simulation**: Use `freezegun` to mock UTC (no real-time waiting).
- **Audit**: Logs are the primary validation (API count, timing, calculation details).
- **Fallback**: Without `freezegun`/`pytest`/`mock`, Scenario 3 and Free Rider tests run constant checks only (no full failure).

```bash
# Run all tests (with time simulation)
pip install freezegun pytest
python -m pytest tests/test_comprehensive_deduction_plan.py -v

# Run without extra deps (fallback constant checks only)
python tests/test_comprehensive_deduction_plan.py

# Run all deduction-related tests
python -m pytest tests/test_comprehensive_deduction_plan.py tests/test_daily_token_deduction.py -v
```

---

## Manual / Staging Checks

- **09:59 UTC**: Run app with `freezegun` at 09:59 UTC; confirm scheduler does not call Bitfinex (no fetch logs).
- **10:00 UTC**: Trigger 10:00 job (or run scheduler with time frozen at 10:00); confirm one API call and snapshot updated.
- **10:30 UTC**: Trigger deduction; confirm no API call and balance reduced by `daily_gross_profit_usd`.
- **Account switch**: Set `api_vault.keys_updated_at` to now; run 10:00 fetch; confirm `account_switch_note` and alert.
