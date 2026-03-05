# Stripe webhook over-credit fix (160k–320k instead of 40k)

## What the logs showed

From `stripe_webhook_debug.log` for user 10, one Whales monthly purchase led to:

| Source | When | Effect |
|--------|------|--------|
| checkout.session.completed (1st) | 18:21:51 | +40,000 → balance 40,000 |
| checkout.session.completed (2nd, same event) | 18:21:53 | +40,000 → balance 80,000 |
| invoice.payment_succeeded (1st, sub_id=None) | 18:21:55 | +40,000 → balance 120,000 |
| invoice.payment_succeeded (2nd, same event) | 18:21:58 | +40,000 → balance 160,000 |
| (Second purchase same user) checkout x2 + invoice x2 | 18:22:46–18:22:54 | +160,000 → balance 320,000 |

So one purchase was credited 4× (checkout twice + invoice twice), and two purchases became 320,000 instead of 80,000.

## Root causes

1. **Same event delivered more than once**  
   Stripe (or the CLI) can send the same `checkout.session.completed` or `invoice.payment_succeeded` event more than once. We were adding tokens every time with no strong idempotency.

2. **checkout idempotency was not race-safe**  
   We only checked `token_ledger` for `stripe_session_id`. Two requests for the same session could both pass the check before either committed, so both added 40k.

3. **invoice added tokens when `sub_id` was None**  
   When `invoice.payment_succeeded` had `sub_id=None`, we never called `subscription_id_already_awarded`, so we always added 40k. So we added once per invoice delivery (and again on retries), even though tokens had already been awarded in checkout.

## Fixes applied

1. **Table `stripe_processed_checkout_sessions`**  
   - Migration: `migrations/add_stripe_processed_checkout_sessions.sql`  
   - Columns: `session_id` (TEXT PRIMARY KEY), `created_at`  
   - Before awarding in `checkout.session.completed`, we `INSERT` the session id. Duplicate (retry or concurrent) gets `IntegrityError` and we skip awarding. One award per session.

2. **Checkout handler**  
   - Resolve `session_id` safely (dict or object).  
   - Call `try_register_checkout_session(db, session_id)` first; if it returns False (already registered), return without adding tokens.  
   - Keep `subscription_session_already_processed` as fallback when the new table is missing.

3. **Invoice handler**  
   - When `sub_id is None`, do **not** add tokens; only update `plan_tier` and `pro_expiry`.  
   - Add tokens in invoice only when `sub_id` is present and `not subscription_id_already_awarded`.  
   - This avoids extra credits when the same invoice is delivered multiple times with `sub_id=None`.

## Run the migration

```bash
psql $DATABASE_URL -f migrations/add_stripe_processed_checkout_sessions.sql
```

Then restart the backend.

## Correcting existing over-credited users

User 10 (and any other user) who received 160k or 320k for a single 40k Whales purchase can be corrected by:

- Running `scripts/fix_user10_stripe_overcredit.py` (or equivalent) to deduct the over-credited amount and optionally add a ledger note, **or**
- Using the admin panel to subtract the extra tokens and record the reason.

See `scripts/fix_user10_stripe_overcredit.py` for a one-off correction script.
