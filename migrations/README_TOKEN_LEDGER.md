# Token ledger migrations

Apply in order:

1. **add_token_ledger_and_balance_columns.sql**  
   Creates `token_ledger` and adds `total_tokens_added`, `total_tokens_deducted`, `purchased_tokens_added` to `user_token_balance`.

   ```bash
   psql $DATABASE_URL -f migrations/add_token_ledger_and_balance_columns.sql
   ```

2. **run_token_ledger_backfill.py**  
   Backfills the new columns from existing `tokens_remaining` and `user_profit_snapshot.gross_profit_usd`, and inserts one `token_ledger` row per user (`reason=migration_backfill`).

   ```bash
   python migrations/run_token_ledger_backfill.py
   ```

3. (Optional, after deploy) **drop_legacy_token_balance_columns.sql**  
   Drops `tokens_remaining` and `purchased_tokens` from `user_token_balance`.

   ```bash
   psql $DATABASE_URL -f migrations/drop_legacy_token_balance_columns.sql
   ```

After step 1 and 2, the app uses the new ledger model. Step 3 can be run later to remove deprecated columns.
