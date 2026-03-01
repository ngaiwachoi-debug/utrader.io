-- =============================================================================
-- Add bot_desired_state to users table (running | stopped). Plan C desired-state.
-- =============================================================================
-- Run: psql $DATABASE_URL -f migrations/add_bot_desired_state.sql
-- Or: python -c "from database import engine; from sqlalchemy import text; engine.execute(text(open('migrations/add_bot_desired_state.sql').read().split('-- ----------')[1].split('-- ----------')[0]))"
-- =============================================================================

-- ---------- PostgreSQL ----------
ALTER TABLE users ADD COLUMN IF NOT EXISTS bot_desired_state VARCHAR(20) DEFAULT 'stopped';

UPDATE users SET bot_desired_state = 'stopped' WHERE bot_desired_state IS NULL;
