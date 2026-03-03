-- Top 100 ranking (fake data), refreshed daily after 10:00 UTC profit run.
-- Run once: psql $DATABASE_URL -f migrations/add_ranking_snapshot.sql

CREATE TABLE IF NOT EXISTS ranking_snapshot (
    rank INTEGER PRIMARY KEY,
    user_display VARCHAR(255) NOT NULL,
    yield_pct DOUBLE PRECISION NOT NULL,
    lent_usd DOUBLE PRECISION DEFAULT 0,
    updated_at TIMESTAMP DEFAULT NOW()
);
