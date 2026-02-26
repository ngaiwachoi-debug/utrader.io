-- Daily token deduction: daily_gross_profit_usd (set at 09:40 UTC, read at 10:15 UTC).
-- Run once: psql $DATABASE_URL -f migrations/add_daily_gross_to_user_profit_snapshot.sql

-- PostgreSQL
ALTER TABLE user_profit_snapshot ADD COLUMN IF NOT EXISTS daily_gross_profit_usd DOUBLE PRECISION DEFAULT 0;
ALTER TABLE user_profit_snapshot ADD COLUMN IF NOT EXISTS last_daily_cumulative_gross DOUBLE PRECISION;
ALTER TABLE user_profit_snapshot ADD COLUMN IF NOT EXISTS last_daily_snapshot_date DATE;
