# Payment function – test steps

## Prerequisites

- Backend running with `.env` loaded (includes `STRIPE_API_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PRICE_*`).
- Frontend running (for UI test).
- **Stripe test mode**: use test keys (`pk_test_...`, `sk_test_...`) and test cards.

---

## Option A: Test from UI

1. **Start backend** (from project root):
   ```bash
   python -m uvicorn main:app --host 127.0.0.1 --port 8000
   ```

2. **Start frontend**:
   ```bash
   cd frontend && npm run dev
   ```

3. **Log in** at http://localhost:3000 (use an account that can access the app).

4. **Open Subscription tab** and click **Subscribe** on a plan (e.g. **Pro Monthly**).

5. You should be redirected to **Stripe Checkout**. Use test card:
   - **Card:** `4242 4242 4242 4242`
   - **Expiry:** any future date (e.g. 12/34)
   - **CVC:** any 3 digits

6. After payment, you should be redirected to `/dashboard?subscription=success` and tokens should be awarded (webhook must run for that).

---

## Option B: Test with script (no UI)

1. **Start backend** (same as above). Ensure `ALLOW_DEV_CONNECT=1` in `.env`.

2. From project root:
   ```bash
   python scripts/test_subscription_tokens.py
   ```
   This creates a test user, gets a JWT, calls `POST /api/create-checkout-session` (Pro monthly), and prints the checkout URL.

3. To open the URL in the browser:
   ```bash
   OPEN_BROWSER=1 python scripts/test_subscription_tokens.py
   ```

4. Complete payment in the browser with test card `4242 4242 4242 4242`, then press Enter in the terminal. The script checks that `tokens_remaining` increased by 2000.

---

## Webhook (so tokens are awarded after payment)

For tokens to be added after a real payment, Stripe must send events to your backend:

- **Local dev:** run Stripe CLI and forward to your backend:
  ```bash
  stripe listen --forward-to http://127.0.0.1:8000/webhook/stripe
  ```
  Copy the `whsec_...` secret and set `STRIPE_WEBHOOK_SECRET` in `.env`, then **restart the backend**.

- **Events used:** `checkout.session.completed`, `invoice.payment_succeeded`.

Without the webhook (or with wrong secret), checkout and payment succeed in Stripe but your app won’t add tokens.

---

## If checkout fails with “No such price” or invalid price

Your `.env` may have **Product IDs** (`prod_...`). Stripe Checkout expects **Price IDs** (`price_...`).

1. In Stripe Dashboard go to **Products** → open the product (e.g. Pro Monthly).
2. In the **Pricing** section, copy the **Price ID** (starts with `price_`).
3. Put that value in the matching `.env` variable (e.g. `STRIPE_PRICE_PRO_MONTHLY="price_..."`).
4. Restart the backend and test again.
