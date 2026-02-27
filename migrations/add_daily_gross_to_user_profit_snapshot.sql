-- =============================================================================
-- Daily token deduction: add daily_gross_profit_usd (set at 09:40 UTC, read at 10:15 UTC).
-- =============================================================================
-- PostgreSQL. Run once: psql $DATABASE_URL -f migrations/add_daily_gross_to_user_profit_snapshot.sql
-- On error: see rollback section at the bottom and docs/ACTIVATE_DEDUCTION.md
-- =============================================================================

-- Apply (idempotent: IF NOT EXISTS)
ALTER TABLE user_profit_snapshot ADD COLUMN IF NOT EXISTS daily_gross_profit_usd DOUBLE PRECISION DEFAULT 0;
ALTER TABLE user_profit_snapshot ADD COLUMN IF NOT EXISTS last_daily_cumulative_gross DOUBLE PRECISION;
ALTER TABLE user_profit_snapshot ADD COLUMN IF NOT EXISTS last_daily_snapshot_date DATE;


-- =============================================================================
-- ROLLBACK (run only if you need to undo the migration)
-- =============================================================================
-- Step 1: Drop columns in any order (PostgreSQL allows DROP COLUMN IF EXISTS).
--
-- ALTER TABLE user_profit_snapshot DROP COLUMN IF EXISTS daily_gross_profit_usd;
-- ALTER TABLE user_profit_snapshot DROP COLUMN IF EXISTS last_daily_cumulative_gross;
-- ALTER TABLE user_profit_snapshot DROP COLUMN IF EXISTS last_daily_snapshot_date;
--
-- Step 2: Restart the app so SQLAlchemy no longer expects these columns.
-- =============================================================================

-- Common errors:
-- - "permission denied": Grant ALTER on user_profit_snapshot to the app user, or run as superuser.
-- - "column already exists": Migration already applied; safe to ignore (or use IF NOT EXISTS).
