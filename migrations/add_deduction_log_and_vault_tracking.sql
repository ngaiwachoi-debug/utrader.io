-- Persisted deduction logs + Bitfinex account change tracking.
-- Run once: psql $DATABASE_URL -f migrations/add_deduction_log_and_vault_tracking.sql

-- api_vault: when API keys are saved (detect account change)
ALTER TABLE api_vault ADD COLUMN IF NOT EXISTS keys_updated_at TIMESTAMP WITH TIME ZONE;

-- user_profit_snapshot: baseline reset when account changes
ALTER TABLE user_profit_snapshot ADD COLUMN IF NOT EXISTS last_vault_updated_at TIMESTAMP WITH TIME ZONE;
ALTER TABLE user_profit_snapshot ADD COLUMN IF NOT EXISTS account_switch_note TEXT;

-- deduction_log: persisted 10:15 UTC deduction history
CREATE TABLE IF NOT EXISTS deduction_log (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    email VARCHAR(255),
    timestamp_utc TIMESTAMP WITH TIME ZONE NOT NULL,
    daily_gross_profit_usd DOUBLE PRECISION DEFAULT 0,
    tokens_deducted DOUBLE PRECISION DEFAULT 0,
    total_used_tokens DOUBLE PRECISION,
    tokens_remaining_after DOUBLE PRECISION,
    account_switch_note TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_deduction_log_user_id ON deduction_log(user_id);
CREATE INDEX IF NOT EXISTS idx_deduction_log_timestamp_utc ON deduction_log(timestamp_utc);
