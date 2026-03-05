# Plan: Fix Whales Plan Token Not Added (uid 2)

## Root cause (from logs)

- **stripe_webhook_debug.log** showed:
  - `checkout.session.completed` had correct metadata: `plan=whales`, `interval=monthly`, `user_id=2`
  - `invoice.payment_succeeded` had **`sub_id=None`**
  - So we never loaded subscription metadata; plan came only from invoice line items and defaulted to `pro` → 2000 tokens instead of 40000

- **Why `sub_id` was None**
  - We read `data.get("subscription")` from the webhook payload.
  - In **newer Stripe API** (e.g. 2025), the Invoice object can use **`parent.subscription_details.subscription`** instead of a top-level `subscription` field. The webhook payload may omit the old field, so we got `None`.
  - Without `sub_id`, we never called `Subscription.retrieve`, so we never had subscription metadata for plan/interval fallback.

## Fixes implemented

1. **Subscription ID extraction (legacy + new API)**
   - Read from:
     - `data.get("subscription")` (legacy)
     - `data.get("parent", {}).get("subscription_details", {}).get("subscription")` (new API)
   - Normalize: accept string ID or dict with `id`.
   - If still missing and we have `invoice.id`, **retrieve the invoice** with `expand=["subscription", "parent"]` and take subscription ID from the retrieved object (legacy or `parent.subscription_details.subscription`).

2. **Plan/interval from invoice parent metadata (new API)**
   - When `_plan_interval_from_invoice` returns default `("pro", "monthly")`, first try **`data.parent.subscription_details.metadata`** (Stripe snapshot on the invoice).
   - If present and valid (`plan` in pro/ai_ultra/whales, `interval` in monthly/yearly), use that for `plan` and `interval` so Whales gets 40000 tokens without needing `Subscription.retrieve`.
   - If still default, keep existing fallback: when `sub_id` is present, call `Subscription.retrieve` and use `sub.metadata` for plan/interval.

3. **Diagnostic logging**
   - Log whether subscription was found from `data.subscription` vs `parent.subscription_details.subscription` and the resolved `sub_id`.
   - Log when plan/interval come from `parent.subscription_details.metadata`.

## Files changed

- **main.py**
  - `invoice.payment_succeeded` handler: robust `sub_id` extraction (legacy + new + retrieve fallback), then plan/interval from `parent.subscription_details.metadata` when available, then existing Subscription.retrieve fallback.
  - Extra `_stripe_webhook_log` for subscription extraction and plan source.

## How to verify

1. Restart backend so new code is loaded.
2. With Stripe CLI forwarding webhooks, have uid 2 (or another test user) complete a **Whales** plan purchase.
3. Check:
   - **stripe_webhook_debug.log**: `sub_id` non-empty (from payload or from retrieve); `invoice plan from parent.subscription_details.metadata plan=whales interval=monthly` or `plan fallback from sub_metadata plan=whales`; `tokens_to_award=40000`.
   - User’s token balance increases by 40000 and token add log shows Whales (monthly).

## If tokens still don’t add

- Inspect **stripe_webhook_debug.log** for the latest `invoice.payment_succeeded` block:
  - Whether `sub_id` is set.
  - Whether `plan from parent.subscription_details.metadata` or `plan fallback from sub_metadata` appears with `plan=whales`.
  - Any `invoice exception` or backend errors.
- Call **GET /admin/stripe-config-check** (as admin) to confirm `STRIPE_PRICE_WHALES_MONTHLY` resolves to the correct product ID so line-item parsing can match when payload is complete.
