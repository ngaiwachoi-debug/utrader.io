# Registration Token E2E & Subscription Integration

## 1. End-to-End Validation: Registration Tokens (150 for New Users)

### Prerequisites

- Backend running (e.g. `uvicorn main:app`) with **`ALLOW_DEV_CONNECT=1`** in `.env`.
- Database accessible (e.g. `psql` or any PostgreSQL client).

### Step-by-step: Create fake test user, verify 150 tokens, clean up

**1a. Create a new test user (triggers registration + 150 token award)**

Use the dev-only endpoint that creates a user by email and awards registration tokens (no Bitfinex keys required). Email must be `@gmail.com`.

```powershell
# PowerShell
$body = '{"email":"test-reg-e2e-' + (Get-Date -Format "yyyyMMddHHmmss") + '@gmail.com"}'
Invoke-RestMethod -Uri "http://127.0.0.1:8000/dev/create-test-user" -Method POST -ContentType "application/json" -Body $body
```

Example response: `{ "user_id": 42, "email": "test-reg-e2e-20250225120000@gmail.com" }`

**Alternative (if you prefer curl):**

```bash
curl -X POST http://127.0.0.1:8000/dev/create-test-user -H "Content-Type: application/json" -d "{\"email\":\"test-reg-e2e-$(date +%s)@gmail.com\"}"
```

**1b. Verify `user_token_balance.tokens_remaining = 150`**

Using the `user_id` from step 1a (or the email), query the database:

```sql
-- Replace 42 with the user_id from step 1a, or use the email below
SELECT u.id, u.email, b.tokens_remaining, b.purchased_tokens
FROM users u
LEFT JOIN user_token_balance b ON b.user_id = u.id
WHERE u.email = 'test-reg-e2e-YYYYMMDDHHMMSS@gmail.com';
```

Expected: one row with `tokens_remaining = 150` and `purchased_tokens = 50` (50 is the registration bonus on top of trial 100 so the API shows 150).

**Optional: verify via API**

```powershell
# Get a JWT for the test user (after creating them)
$loginBody = '{"email":"test-reg-e2e-YYYYMMDDHHMMSS@gmail.com"}'
$login = Invoke-RestMethod -Uri "http://127.0.0.1:8000/dev/login-as" -Method POST -ContentType "application/json" -Body $loginBody
# Then GET /user-status/{user_id} with header Authorization: Bearer <token>
# tokens_remaining in the response should be 150
```

**1c. Clean up the test user**

```sql
-- Replace with the actual test user email from step 1a
DELETE FROM user_token_balance WHERE user_id = (SELECT id FROM users WHERE email = 'test-reg-e2e-YYYYMMDDHHMMSS@gmail.com');
DELETE FROM users WHERE email = 'test-reg-e2e-YYYYMMDDHHMMSS@gmail.com';
```

If you have other tables that reference `users.id` (e.g. `api_vault`, `performance_log`), delete or null out those first as needed for your schema.

---

## 2. Stripe environment variables

See **[STRIPE_ENV_SETUP.md](STRIPE_ENV_SETUP.md)** for the full list of required variables (monthly + yearly price IDs, webhook secret) and PowerShell/terminal setup.

---

## 3. Subscription Button Backend Integration Report

### Status: **Connected** (monthly and yearly plans)

| Area | Status | Details |
|------|--------|---------|
| Frontend → API on button click | ✅ Connected | "Subscribe to Pro / AI Ultra / Whales" call `POST /api/create-checkout-session` with `{ plan, interval: "monthly" }`. |
| Backend checkout endpoint | ✅ Exists | `POST /api/create-checkout-session` in `main.py`; validates `plan` and `interval`, maps to Stripe Price IDs. |
| Plan ID → Stripe Price ID | ✅ Mapped | Uses env: `STRIPE_PRICE_PRO_MONTHLY`, `STRIPE_PRICE_AI_ULTRA_MONTHLY`, `STRIPE_PRICE_WHALES_MONTHLY`. |
| Post-payment (Stripe webhook) | ✅ Implemented | `invoice.payment_succeeded` updates `users.plan_tier`, `rebalance_interval`, `lending_limit`, `pro_expiry`. |
| Token credits after subscription | ✅ By design | No separate “award” to `purchased_tokens`. Credits come from plan tier: `get_user_status` uses `PLAN_TOKEN_CREDITS[plan_tier]` (Pro 1500, AI Ultra 9000, Whales 40000) as `initial_credit`; so after webhook sets `plan_tier`, the user’s token balance is 1500 / 9000 / 40000. |

### Frontend (what is sent)

- **Endpoint:** `POST ${API_BASE}/api/create-checkout-session`
- **Headers:** `Content-Type: application/json`, `Authorization: Bearer <JWT>`
- **Body:** `{ "plan": "pro" | "ai_ultra" | "whales", "interval": "monthly" }`
- **User identification:** JWT from `getBackendToken()` (no user_id in body; backend uses `current_user` from JWT).

### Backend (what exists)

- **Endpoint:** `main.py` → `create_checkout_session(payload: CreateCheckoutPayload, current_user: ...)`.
- **Plan → Price ID:** `STRIPE_PRICE_PRO_MONTHLY`, `STRIPE_PRICE_AI_ULTRA_MONTHLY`, `STRIPE_PRICE_WHALES_MONTHLY` (env).
- **Webhook:** `POST /webhook/stripe` handles `checkout.session.completed` (one-off token purchases) and `invoice.payment_succeeded` (subscription renewals). For subscriptions it:
  - Finds user by `customer_email` / `customer_details.email`
  - Reads `plan` from subscription metadata (`stripe.Subscription.retrieve(sub_id).metadata.plan`)
  - Sets `user.plan_tier`, `user.rebalance_interval`, `user.lending_limit`, `user.pro_expiry`
  - Does **not** write to `user_token_balance.purchased_tokens` for plans; token allowance is implied by `plan_tier` in `get_user_status`.

### Token awards on subscription payment

The Stripe webhook `invoice.payment_succeeded` now adds plan-specific tokens to `user_token_balance.purchased_tokens` (adds to existing, does not overwrite):

- **Monthly:** Pro +2000, AI Ultra +9000, Whales AI +40000  
- **Yearly:** Pro +24000, AI Ultra +108000, Whales AI +480000  

Audit log: `subscription_token_award user_id=... plan=... interval=... tokens_added=... timestamp=...`

### Missing / optional pieces

1. **Yearly plans** are now supported: frontend has yearly buttons ($192 / $576 / $1920 per year), backend accepts `interval: "yearly"` and uses `STRIPE_PRICE_*_YEARLY` env vars.

2. **Env required for subscriptions**  
   - `STRIPE_API_KEY`, `STRIPE_WEBHOOK_SECRET`  
   - `STRIPE_PRICE_PRO_MONTHLY`, `STRIPE_PRICE_AI_ULTRA_MONTHLY`, `STRIPE_PRICE_WHALES_MONTHLY`  
   - Without these, checkout returns 503.

3. **No extra “subscription token award” needed**  
   - Plan token credits (1500 / 9000 / 40000) are applied via `plan_tier` in `get_user_status`; no additional snippet to award tokens on subscription payment is required.

---

## 3. Optional: Add Yearly Subscription Support

If you later add yearly plans (e.g. “Subscribe to Pro Yearly”):

**Backend:** extend `create_checkout_session` to accept `interval == "yearly"` and map to env vars such as `STRIPE_PRICE_PRO_YEARLY`, etc., and create the session with the yearly price ID.

**Webhook:** keep using subscription metadata `plan`; optionally set `interval_days = 365` when `interval == "yearly"` for `pro_expiry`.

**Frontend:** pass `interval: "yearly"` when the user selects the yearly option and call the same `POST /api/create-checkout-session` with the same `plan` and `interval: "yearly"`.

---

## 4. Subscription token E2E script (optional)

Run the script to create a test user, open Monthly Pro checkout, and verify +2000 tokens after payment:

```powershell
# From project root; backend must be running with ALLOW_DEV_CONNECT=1 and Stripe env set
python scripts/test_subscription_tokens.py
```

Then complete payment in the browser with test card `4242 4242 4242 4242`. The script verifies `tokens_remaining` increased by 2000 and prints cleanup SQL. See script docstring for `API_BASE` and `OPEN_BROWSER` env options.

---

## Summary

- **E2E registration:** Use `POST /dev/create-test-user` with a unique `@gmail.com` email, then check `user_token_balance.tokens_remaining = 150`, then delete the test user and their token row.
- **Subscription buttons:** Connected for monthly and yearly Pro / AI Ultra / Whales; webhook awards plan tokens to `purchased_tokens` (2000/9000/40000 monthly; 24000/108000/480000 yearly) and logs the award.
- **Stripe env:** See [STRIPE_ENV_SETUP.md](STRIPE_ENV_SETUP.md) for all required variables and setup.
