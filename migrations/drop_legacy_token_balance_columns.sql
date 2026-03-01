-- Drop deprecated columns from user_token_balance (run after backfill and code switch).
-- Run once: psql $DATABASE_URL -f migrations/drop_legacy_token_balance_columns.sql

ALTER TABLE user_token_balance DROP COLUMN IF EXISTS tokens_remaining;
ALTER TABLE user_token_balance DROP COLUMN IF EXISTS purchased_tokens;
