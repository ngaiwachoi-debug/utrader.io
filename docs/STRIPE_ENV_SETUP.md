# Stripe Environment Variables (Subscription + Tokens)

Required for subscription checkout and token purchases. Set these in your backend `.env` (or export in the shell before starting the server).

---

## Required variables

| Variable | Description | Example (replace with your Stripe Dashboard values) |
|----------|-------------|------------------------------------------------------|
| `STRIPE_API_KEY` | Stripe secret key (live or test) | `sk_test_51ABC...` or `sk_live_...` |
| `STRIPE_WEBHOOK_SECRET` | Webhook signing secret (from Stripe Dashboard → Developers → Webhooks) | `whsec_...` |

---

## Monthly subscription price IDs

Create recurring **monthly** prices in Stripe (Products → your plan → Add price → Recurring, Monthly).

| Variable | Plan | Suggested price |
|----------|------|------------------|
| `STRIPE_PRICE_PRO_MONTHLY` | Pro Monthly | $20/month |
| `STRIPE_PRICE_AI_ULTRA_MONTHLY` | AI Ultra Monthly | $60/month |
| `STRIPE_PRICE_WHALES_MONTHLY` | Whales AI Monthly | $200/month |

Example values: `price_1ABC...`, `price_2DEF...`, `price_3GHI...`

---

## Yearly subscription price IDs

Create recurring **yearly** prices in Stripe (Products → your plan → Add price → Recurring, Yearly).

| Variable | Plan | Suggested price |
|----------|------|------------------|
| `STRIPE_PRICE_PRO_YEARLY` | Pro Yearly | $192/year |
| `STRIPE_PRICE_AI_ULTRA_YEARLY` | AI Ultra Yearly | $576/year |
| `STRIPE_PRICE_WHALES_YEARLY` | Whales AI Yearly | $1920/year |

Example values: `price_4JKL...`, `price_5MNO...`, `price_6PQR...`

---

## Setting variables in the dev environment

### PowerShell (Windows)

```powershell
# One-time per session (current terminal only)
$env:STRIPE_API_KEY = "sk_test_51ABC..."
$env:STRIPE_WEBHOOK_SECRET = "whsec_..."
$env:STRIPE_PRICE_PRO_MONTHLY = "price_1ABC..."
$env:STRIPE_PRICE_AI_ULTRA_MONTHLY = "price_2DEF..."
$env:STRIPE_PRICE_WHALES_MONTHLY = "price_3GHI..."
$env:STRIPE_PRICE_PRO_YEARLY = "price_4JKL..."
$env:STRIPE_PRICE_AI_ULTRA_YEARLY = "price_5MNO..."
$env:STRIPE_PRICE_WHALES_YEARLY = "price_6PQR..."

# Then start the backend
uvicorn main:app --reload
```

**Persist in `.env` (recommended):** create or edit `.env` in the project root (backend directory):

```powershell
# .env (do not commit real keys to git)
STRIPE_API_KEY=sk_test_51ABC...
STRIPE_WEBHOOK_SECRET=whsec_...
STRIPE_PRICE_PRO_MONTHLY=price_1ABC...
STRIPE_PRICE_AI_ULTRA_MONTHLY=price_2DEF...
STRIPE_PRICE_WHALES_MONTHLY=price_3GHI...
STRIPE_PRICE_PRO_YEARLY=price_4JKL...
STRIPE_PRICE_AI_ULTRA_YEARLY=price_5MNO...
STRIPE_PRICE_WHALES_YEARLY=price_6PQR...
```

If your app loads `.env` (e.g. with `python-dotenv`), no need to export in the terminal.

---

### Bash / WSL / macOS terminal

```bash
# One-time per session
export STRIPE_API_KEY="sk_test_51ABC..."
export STRIPE_WEBHOOK_SECRET="whsec_..."
export STRIPE_PRICE_PRO_MONTHLY="price_1ABC..."
export STRIPE_PRICE_AI_ULTRA_MONTHLY="price_2DEF..."
export STRIPE_PRICE_WHALES_MONTHLY="price_3GHI..."
export STRIPE_PRICE_PRO_YEARLY="price_4JKL..."
export STRIPE_PRICE_AI_ULTRA_YEARLY="price_5MNO..."
export STRIPE_PRICE_WHALES_YEARLY="price_6PQR..."

# Then start the backend
uvicorn main:app --reload
```

Or add the same lines to `.env` and load it (e.g. `set -a; source .env; set +a` or use `python-dotenv`).

---

## Webhook endpoint URL

For local testing, use Stripe CLI to forward events:

```bash
stripe listen --forward-to http://127.0.0.1:8000/webhook/stripe
```

Use the printed `whsec_...` as `STRIPE_WEBHOOK_SECRET` in your local `.env`. For production, create a webhook in Stripe Dashboard pointing to `https://your-api.com/webhook/stripe` and subscribe to `checkout.session.completed` and `invoice.payment_succeeded`.

---

## Token awards (reference)

After a successful subscription payment, the webhook adds these to `user_token_balance.purchased_tokens`:

| Plan   | Interval | Tokens added |
|--------|----------|--------------|
| Pro    | Monthly  | 2000         |
| Pro    | Yearly   | 24000        |
| AI Ultra | Monthly | 9000       |
| AI Ultra | Yearly  | 108000      |
| Whales AI | Monthly | 40000    |
| Whales AI | Yearly  | 480000      |
