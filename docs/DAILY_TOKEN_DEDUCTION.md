# Daily Token Deduction (10:15 UTC)

Automated daily token deduction based on **daily gross profit** (stored at 09:40 UTC from the Bitfinex refresh).

## Flow

1. **09:40 UTC** – Daily gross profit refresh runs; for each user, `user_profit_snapshot.daily_gross_profit_usd` is set (delta from previous day’s cumulative gross).
2. **10:15 UTC** – Deduction job runs:
   - For each user with `user_token_balance` and `user_profit_snapshot`:
   - If `daily_gross_profit_usd <= 0`: skip (no deduction).
   - Else: `new_tokens_remaining = tokens_remaining - daily_gross_profit` (1:1 USD); clamp to 0.
   - Update `last_gross_usd_used` and `updated_at`.

## Behaviour

- **Formula**: `new_tokens_remaining = tokens_remaining - daily_gross_profit`; if &lt; 0 then set to 0.
- **Negative profit**: no deduction (balance unchanged).
- **Retries**: 3 attempts, 5 minutes apart, on failure.
- **Alerts**: On final failure, an entry is added to the API failures list; if `DEDUCTION_ALERT_WEBHOOK_URL` is set (Slack incoming webhook), a message is sent (requires `aiohttp` if using webhook).

## Database

- **Migration**: Run `migrations/add_daily_gross_to_user_profit_snapshot.sql` to add `daily_gross_profit_usd`, `last_daily_cumulative_gross`, `last_daily_snapshot_date` to `user_profit_snapshot`.

## Running

- **With API**: When `uvicorn main:app` is running, the 10:15 job is scheduled in-process; no cron needed.
- **Without API**: Run `python scripts/daily_token_deduction_1015utc.py` via cron at 10:15 UTC, e.g. `15 10 * * * cd /path/to/buildnew && python scripts/daily_token_deduction_1015utc.py`.

## Tests

- **Unit**: `python tests/test_daily_token_deduction.py` or `pytest tests/test_daily_token_deduction.py -v`
- **Cases**: (1) tokens_remaining=2000, profit=500 → 1500; (2) tokens_remaining=100, profit=200 → 0; (3) profit=-50 → unchanged.
