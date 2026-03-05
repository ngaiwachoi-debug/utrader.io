-- Idempotency for Stripe checkout.session.completed: one token award per session (avoids double-add on retries/duplicates).
-- Run once: psql $DATABASE_URL -f migrations/add_stripe_processed_checkout_sessions.sql

CREATE TABLE IF NOT EXISTS stripe_processed_checkout_sessions (
    session_id TEXT PRIMARY KEY,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);
