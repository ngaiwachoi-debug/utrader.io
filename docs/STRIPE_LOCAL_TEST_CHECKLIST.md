# Stripe webhook – local test checklist

Use this when testing subscription (e.g. Whales) payments on your **local** server so tokens are added correctly.

---

## 1. Start Stripe CLI listener (required)

Stripe cannot call `localhost` directly. The CLI forwards events to your app.

```bash
stripe listen --forward-to http://127.0.0.1:8000/webhook/stripe
```

**Leave this terminal open** while you test.

You’ll see something like:

```
Ready! Your webhook signing secret is whsec_xxxxxxxxxxxxxxxxxxxxxxxx
```

---

## 2. Put the **current** secret in `.env`

- Copy the **full** `whsec_...` value from the `stripe listen` output **from this run**.
- In project root, open `.env`.
- Set:
  ```env
  STRIPE_WEBHOOK_SECRET=whsec_xxxxxxxxxxxxxxxxxxxxxxxx
  ```
- **Important:** Every time you run `stripe listen` you get a **new** secret. If you restart the listener, update `.env` and restart the backend.

---

## 3. Restart the backend

After changing `STRIPE_WEBHOOK_SECRET` (or any Stripe vars in `.env`):

```bash
# Stop the backend (Ctrl+C or kill the process), then:
cd c:\Users\choiw\Desktop\bifinex\buildnew
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

---

## 4. Optional: turn on webhook debug logs

In `.env`:

```env
STRIPE_WEBHOOK_DEBUG=1
```

Then restart the backend. Each webhook will be appended to:

**`stripe_webhook_debug.log`** (in project root).

Check for lines like:

- `checkout.session.completed metadata=...` or `fallback from subscription metadata ...`
- `checkout.session.completed subscription_token_award user_id=... plan=whales ... tokens_added=40000 ...`

If you see `subscription_token_award ... tokens_added=40000`, the backend is crediting Whales correctly.

---

## 5. Run a test payment

1. Frontend: http://localhost:3000 (or 3000/en).
2. Log in (or use “Dev: Login as” if enabled).
3. Open Subscription and choose **Whales** (e.g. monthly).
4. Complete checkout (test card: `4242 4242 4242 4242`).
5. After success, check:
   - Dashboard / token balance: should increase by **40,000** for Whales monthly.
   - `stripe_webhook_debug.log`: should show `checkout.session.completed` and `subscription_token_award ... 40000`.

---

## If tokens still don’t add

| Check | What to do |
|--------|------------|
| **400 from Stripe** | Webhook secret is wrong. Get a new one from the **current** `stripe listen` and update `STRIPE_WEBHOOK_SECRET` in `.env`, then restart backend. |
| **No log lines** | `stripe listen` not running, or not forwarding to `http://127.0.0.1:8000/webhook/stripe`. Start it and try again. |
| **Log shows 200 but no token line** | Set `STRIPE_WEBHOOK_DEBUG=1`, restart backend, pay again, then open `stripe_webhook_debug.log` and look for `checkout.session.completed` and any error line. |
| **Wrong amount (e.g. 2000)** | Old code or wrong handler. Ensure backend was restarted after the latest webhook changes; tokens for subscriptions are awarded in `checkout.session.completed` (and idempotently in `invoice.payment_succeeded`). |

---

## Summary

1. Run **`stripe listen --forward-to http://127.0.0.1:8000/webhook/stripe`** and keep it running.
2. Put the printed **`whsec_...`** in `.env` as **`STRIPE_WEBHOOK_SECRET`**.
3. Restart the **backend**.
4. Do a test Whales purchase and check balance + `stripe_webhook_debug.log`.
