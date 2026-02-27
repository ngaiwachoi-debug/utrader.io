# Daily Token Deduction & Bitfinex Account Changes

## Timing (no API before 10:00 UTC)

- **10:00 UTC**: Single daily Bitfinex API call per user – fetch full Margin Funding Payment ledger. Store gross and daily in `user_profit_snapshot`. If ledger data is incomplete (latest entry &lt; 20 mins old), do not save.
- **10:10 UTC**: One retry only for users whose 10:00 fetch was incomplete (max 2 API calls/day per user).
- **10:30 UTC**: Daily token deduction – uses stored `daily_gross_profit_usd` only (no Bitfinex API call). 30-minute buffer after API ensures finalized data.

## Rules

1. **Daily deduction (10:30 UTC)** runs every day for all users with a vault and token balance, even if they change their Bitfinex account mid-cycle.
2. **Unit clarity**: Gross Profit = USD; Used Tokens = `int(gross_profit_usd × 10)` (see `TOKENS_PER_USDT_GROSS = 10` in `main.py`).
3. **Account change**: When a user updates their Bitfinex API keys (new account), the 10:00 UTC job detects it via `api_vault.keys_updated_at`, sets `account_switch_note`; 10:30 UTC then deducts only from the new account’s daily gross (1:1 USD → tokens deducted). Existing token balance is preserved.
4. **Incomplete data**: If after 10:10 retry the ledger is still incomplete, set `daily_gross_profit_usd = 0` for that user (skip deduction for the day), log and alert admins. Do not use partial data.

## Consistency (Gross Profit vs Used Tokens)

- **Formula**: `used_tokens = int(gross_profit_usd × TOKENS_PER_USDT_GROSS)` with `TOKENS_PER_USDT_GROSS = 10`.
- **Example**: Gross Profit 72.20 USD → Used Tokens = 722 (not 739). A snapshot showing 73.9 USD would yield 739 tokens; that indicates the snapshot needs reconciliation to the actual Margin Funding Payment sum (e.g. 72.20).

## Reconciling snapshot to correct Gross Profit (e.g. 72.20)

To fix a user’s displayed Gross Profit and Used Tokens to match the real Bitfinex data (e.g. sum of Margin Funding Payment entries = 72.201934 → 72.20):

```bash
python scripts/seed_gross_profit_snapshot.py choiwangai@gmail.com 72.20
```

After this, Gross Profit shows 72.20 USD and Used Tokens = 722.

## Persisted logs and admin API

- **Deduction logs** are stored in the `deduction_log` table (user_id, email, timestamp_utc, daily_gross_profit_usd, tokens_deducted, total_used_tokens, account_switch_note, etc.).
- **GET /admin/deduction/logs** returns persisted entries (with optional `start_date` / `end_date`). Each entry includes `email` and `account_switch_note` when the user had switched Bitfinex accounts.
- **Account switch**: When the 10:00 job detects a new `keys_updated_at`, it sets `account_switch_note` on the snapshot and logs a warning; admins are alerted via `DEDUCTION_ALERT_WEBHOOK_URL` (e.g. Slack).

## Migration

Run once to add deduction_log and vault/snapshot tracking columns:

```bash
psql $DATABASE_URL -f migrations/add_deduction_log_and_vault_tracking.sql
```
