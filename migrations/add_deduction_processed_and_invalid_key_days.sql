-- Prevent double-charge and late-fee tracking. Run once: psql $DATABASE_URL -f migrations/add_deduction_processed_and_invalid_key_days.sql

-- user_profit_snapshot: deduction already run for date, invalid key days, cached amount for reconciliation
ALTER TABLE user_profit_snapshot ADD COLUMN IF NOT EXISTS deduction_processed BOOLEAN DEFAULT FALSE;
ALTER TABLE user_profit_snapshot ADD COLUMN IF NOT EXISTS last_deduction_processed_date DATE;
ALTER TABLE user_profit_snapshot ADD COLUMN IF NOT EXISTS invalid_key_days INTEGER DEFAULT 0;
ALTER TABLE user_profit_snapshot ADD COLUMN IF NOT EXISTS last_cached_daily_gross_usd DOUBLE PRECISION;
