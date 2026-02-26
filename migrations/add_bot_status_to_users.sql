-- =============================================================================
-- Add bot_status to users table (stopped | starting | running).
-- =============================================================================
-- Run by database type (see below). If migration fails, see DEBUG_GUIDE in
-- docs/BOT_LIFECYCLE_ARCHITECTURE.md or run: python migrations/run_bot_status_migration.py
-- =============================================================================

-- ---------- PostgreSQL ----------
-- Safe to run multiple times (IF NOT EXISTS).
ALTER TABLE users ADD COLUMN IF NOT EXISTS bot_status VARCHAR(20) DEFAULT 'stopped';

-- Optional: backfill (uncomment if needed)
-- UPDATE users SET bot_status = 'stopped' WHERE bot_status IS NULL;


-- ---------- SQLite ----------
-- SQLite does not support "ADD COLUMN IF NOT EXISTS" in older versions.
-- Run ONLY ONE of the following, depending on how you execute:
--
-- Option A (sqlite3 CLI, run once; if "duplicate column name" then already applied):
--   sqlite3 your.db "ALTER TABLE users ADD COLUMN bot_status VARCHAR(20) DEFAULT 'stopped';"
--
-- Option B (Python runner that ignores "column already exists"):
--   python migrations/run_bot_status_migration.py
-- =============================================================================
