-- Add plan_tier to ranking_snapshot (trial, pro, ai_ultra, whales).
-- Run once: sqlite3 db or psql $DATABASE_URL -f migrations/add_ranking_plan_tier.sql

-- SQLite
ALTER TABLE ranking_snapshot ADD COLUMN plan_tier VARCHAR(32);
