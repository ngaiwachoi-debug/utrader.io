-- Post-11:15 reconciliation sweep (23:00 UTC) and persistent key deletion counts.
-- Run once: psql $DATABASE_URL -f migrations/add_reconciliation_completed_and_key_deletions.sql

-- user_profit_snapshot: 23:00 reconciliation completed for key restored post-11:15
ALTER TABLE user_profit_snapshot ADD COLUMN IF NOT EXISTS reconciliation_completed BOOLEAN DEFAULT TRUE;

-- users: monthly key deletion counts (JSONB or JSON); default '{}'
-- PostgreSQL: use JSONB; if your DB uses JSON type, change to JSON
ALTER TABLE users ADD COLUMN IF NOT EXISTS key_deletions TEXT DEFAULT '{}';
