# Token Add Log: Keep & Show All Information

## Goal
When users deposit, join tier plans, or receive token adds (admin, registration), the token add log should **keep and show** all relevant information in both admin and user-facing views.

## Current State
- **Storage**: `token_ledger` table stores `user_id`, `activity_type` ('add'), `amount`, `reason`, `created_at`, and `extra` (JSONB).
- **Reasons**: `registration`, `admin_add`, `admin_bulk_add`, `deposit_usd`, `subscription_monthly`, `subscription_yearly`, `deduction_rollback`, `migration_backfill`.
- **Gaps**: Many call sites do not pass `extra`; APIs return only `reason` (no plan name, USD amount, or interval), so logs are not fully informative.

## Plan

### 1. Backend – Store full context in `extra` at every add path
- **Registration**: Keep as-is (reason is enough).
- **Admin add** (`POST /admin/users/{id}/tokens/add`): Add optional `note` to request body; store `extra={"note": note, "added_by": admin_email}`.
- **Admin bulk add**: Store `extra={"batch": True}` for consistency.
- **Deposit (pay-as-you-go)**  
  - Bypass: `extra={"usd_amount": amount_float}`.  
  - Stripe `checkout.session.completed` (tokens_deposit): `extra={"usd_amount": amount_usd}`.
- **Subscription (Stripe `invoice.payment_succeeded`)**: Already has `stripe_invoice_id`; add `extra={"plan": plan, "interval": interval}`.
- **Subscription bypass**: `extra={"plan": plan, "interval": interval}`.
- **Deduction rollback**: `extra={"rollback_date": date_str}` when available.

### 2. Backend – API response: add human-readable `detail`
- Add optional `detail: Optional[str]` to `TokenAddLogEntry` (admin) and `TokenAddHistoryEntry` (user).
- Helper `_token_add_detail(reason, extra)` in main.py:
  - `subscription_monthly` / `subscription_yearly` + extra: e.g. "Whales AI (monthly)".
  - `deposit_usd` + `usd_amount`: "Deposit $25".
  - `admin_add` + `note`: "Admin: {note}" or "Admin adjustment".
  - `deduction_rollback` + `rollback_date`: "Refund (rollback {date})".
  - Else: use existing reason label (registration, migration_backfill, etc.).
- Populate `detail` when building list responses for `GET /admin/token-add/logs` and `GET /api/v1/users/me/token-add-history`. If `extra` is missing for old rows, derive from reason only.

### 3. Backend – Table existence and safety
- Admin endpoint already returns `[]` when `token_ledger` is missing; ensure user endpoint does not 500 when table is missing (check table existence or catch and return []).

### 4. Frontend – Display detail
- **Admin (Token add log)**: Add column "Detail" showing `entry.detail` when present; otherwise show reason.
- **User (Settings → Token activity)**: Show `entry.detail` when present; otherwise keep `tokenAddReasonLabel(e.reason)`.

### 5. No breaking changes
- All new fields are additive (`detail` optional, `extra` keys optional). Existing rows without `extra` still display via reason-only detail.

## Implementation order
1. Add `extra` at all `add_tokens` call sites in main.py.
2. Add `_token_add_detail` and extend Pydantic models with `detail`.
3. Populate `detail` in admin and user token-add-history endpoints (read `extra` from TokenLedger; model may use `.extra` or raw SQL for JSONB).
4. Frontend: admin table + user settings token add table show `detail` when present.
