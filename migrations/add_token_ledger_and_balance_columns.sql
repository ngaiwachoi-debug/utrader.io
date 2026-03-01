-- Token ledger + user_token_balance columns for traceable add/deduct model.
-- Run once: psql $DATABASE_URL -f migrations/add_token_ledger_and_balance_columns.sql

-- token_ledger: append-only log for every add/deduct
CREATE TABLE IF NOT EXISTS token_ledger (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id),
    activity_type VARCHAR(16) NOT NULL,
    amount DOUBLE PRECISION NOT NULL,
    reason VARCHAR(64) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
    metadata JSONB
);
CREATE INDEX IF NOT EXISTS idx_token_ledger_user_id_created_at ON token_ledger(user_id, created_at);

-- user_token_balance: add running totals (keep existing columns for backfill)
ALTER TABLE user_token_balance ADD COLUMN IF NOT EXISTS total_tokens_added DOUBLE PRECISION NOT NULL DEFAULT 0;
ALTER TABLE user_token_balance ADD COLUMN IF NOT EXISTS total_tokens_deducted DOUBLE PRECISION NOT NULL DEFAULT 0;
-- Optional: cache for referral "purchased" amount (adds from deposit/subscription/admin)
ALTER TABLE user_token_balance ADD COLUMN IF NOT EXISTS purchased_tokens_added DOUBLE PRECISION NOT NULL DEFAULT 0;
