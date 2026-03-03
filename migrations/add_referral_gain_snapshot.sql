-- Top 100 referral gain (fake data), refreshed daily after 10:00 UTC profit run.
-- Run once: psql $DATABASE_URL -f migrations/add_referral_gain_snapshot.sql

CREATE TABLE IF NOT EXISTS referral_gain_snapshot (
    rank INTEGER PRIMARY KEY,
    user_display VARCHAR(255) NOT NULL,
    usdt_gain_daily DOUBLE PRECISION NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW()
);
