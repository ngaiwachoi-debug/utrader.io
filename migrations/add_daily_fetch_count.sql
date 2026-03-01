-- Duplicate API call prevention: max 2 fetches per user per day (10:00 + 10:10 retry).
-- Run once: psql $DATABASE_URL -f migrations/add_daily_fetch_count.sql

ALTER TABLE user_profit_snapshot ADD COLUMN IF NOT EXISTS daily_fetch_date DATE;
ALTER TABLE user_profit_snapshot ADD COLUMN IF NOT EXISTS daily_fetch_count INTEGER DEFAULT 0;
