# Deduction multiplier (admin setting) – implementation plan

## Goal
Manual trigger (and scheduled) token deduction should use: **deduction amount = daily_gross × multiplier**. The multiplier is configurable in admin settings (default 1.0 = current 1:1 behavior).

## Current behavior
- **Formula today:** `tokens_deducted = daily_gross` (1 USD gross = 1 token).
- **Where:** `services/daily_token_deduction.py`: `run_deduction_for_user_for_date` (line ~78) and `run_daily_token_deduction` (line ~167) both set `tokens_deducted = daily_gross`.
- **Callers:** 
  - 10:30 UTC scheduler: `run_daily_token_deduction(db)`
  - Manual trigger: backfill uses `run_deduction_for_user_for_date`, then `run_daily_token_deduction(db)`
  - 11:15 catch-up: `run_daily_token_deduction(db, user_ids=...)`

## Design

### 1. Admin setting
- **Key:** `deduction_multiplier`
- **Storage:** `admin_settings` table (key/value), same as `daily_deduction_utc_hour`, `min_withdrawal_usdt`, etc.
- **Default:** `1.0` (no change to current behavior).
- **Validation:** Must be > 0 and reasonable (e.g. 0.01–100). Backend and frontend validate.

### 2. Backend

| File | Change |
|------|--------|
| **main.py** | Add `deduction_multiplier` to `AdminSettingsUpdateBody` (optional float). In `admin_get_settings`, add key `"deduction_multiplier"` and default `"1"`. In `admin_update_settings`, handle `body.deduction_multiplier` and persist. Add helper `_get_deduction_multiplier(db)` → float (read from admin_settings, default 1.0). |
| **main.py** | **Manual trigger** (`POST /admin/deduction/trigger`): Before backfill loop and before `run_daily_token_deduction`, get `multiplier = _get_deduction_multiplier(db)`. Pass `deduction_multiplier=multiplier` into `run_deduction_for_user_for_date` and `run_daily_token_deduction`. |
| **main.py** | **10:30 scheduler** (`_run_daily_token_deduction_scheduler`): Get multiplier from DB (new session) via `_get_deduction_multiplier(db)` and pass into `run_daily_token_deduction(db, deduction_multiplier=multiplier)`. |
| **main.py** | **11:15 catch-up**: Same: read multiplier, pass into `run_daily_token_deduction(db, user_ids=..., deduction_multiplier=multiplier)`. |
| **services/daily_token_deduction.py** | `run_deduction_for_user_for_date(..., deduction_multiplier: float = 1.0)`: Compute `amount_to_deduct = round(daily_gross * deduction_multiplier, 2)`. Use `amount_to_deduct` (not `daily_gross`) for `apply_deduction_rule`, `deduct_tokens`, and log. Referral `purchased_burned` should stay based on actual tokens taken (amount_to_deduct). |
| **services/daily_token_deduction.py** | `run_daily_token_deduction(..., deduction_multiplier: float = 1.0)`: Same: `tokens_deducted = round(daily_gross * deduction_multiplier, 2)`. Use that for deduction and log. |

### 3. Frontend (admin)
- **GET /admin/settings** already returns whatever keys the backend sends. Add `deduction_multiplier` to the keys list and default → it will appear in the generic settings form (one row per key).
- **Save:** In `AdminSettingsFormInline` (admin page), when building the update body, add `deduction_multiplier`: parse `local.deduction_multiplier` as float and send (with validation, e.g. 0.01–100).

### 4. Migration / seed
- Optional: seed `deduction_multiplier` = `"1"` in existing deployments (e.g. in `migrate_admin_tables.py` or a one-off SQL). If not seeded, `_get_deduction_multiplier` returns 1.0 when key is missing.

### 5. Logging and display
- Deduction log entries already store `tokens_deducted` and `daily_gross_profit_usd`. No schema change. Optionally log multiplier in admin audit when trigger runs (e.g. `{"count": N, "deduction_multiplier": 1.5}`).

### 6. Tests
- Update tests that assert `tokens_deducted == daily_gross` to either pass `deduction_multiplier=1.0` or assert `tokens_deducted == daily_gross * multiplier` when multiplier is set.
- Add a short test: multiplier 2.0 → tokens_deducted = 2 * daily_gross.

## Implementation order
1. **Backend: admin setting** – Add key, default, update body, getter, validation (e.g. clamp to 0.01–100).
2. **Backend: deduction service** – Add `deduction_multiplier` parameter to both functions; use it to compute `tokens_deducted`.
3. **Backend: callers** – Scheduler, manual trigger, and catch-up pass multiplier from `_get_deduction_multiplier(db)`.
4. **Frontend: admin** – Parse and send `deduction_multiplier` on save; optional client-side validation.
5. **Seed default** – Ensure new or existing DBs have `deduction_multiplier` = 1.0 if desired (or rely on default in code).
6. **Tests** – Adjust existing deduction tests; add one for multiplier ≠ 1.

## Edge cases
- **Multiplier &lt; 0 or 0:** Reject or treat as 1.0 (backend validation).
- **Very large multiplier:** Cap at e.g. 100 to avoid accidental huge deductions.
- **Referral:** `purchased_burned` is used for referral rewards; keep it based on the actual tokens deducted (amount_to_deduct), so referral logic stays consistent.

## Rollback
- Set `deduction_multiplier` to `1` in admin settings. No code revert needed unless desired.
