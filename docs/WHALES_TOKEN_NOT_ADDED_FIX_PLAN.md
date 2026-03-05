# Plan: Fix Whales Plan Token Not Added (sub_id None in Webhook)

**Status: Implemented** (in `main.py` invoice.payment_succeeded handler).

## Root cause (from logs)

`stripe_webhook_debug.log` shows:

- `checkout.session.completed` has correct metadata: `plan=whales`, `interval=monthly`, `user_id=2`.
- `invoice.payment_succeeded` log shows **`sub_id=None`**.
- Because `sub_id` is None:
  1. We never run subscription metadata lookup for user (we still find user by email ✓).
  2. We never run the plan/interval fallback from subscription metadata (the condition is `if (plan, interval) == ("pro", "monthly") and sub_id`).
- `_plan_interval_from_invoice(data)` returns default `("pro", "monthly")` (invoice line items not matching or not present in payload).
- Result: we award 2000 tokens (Pro monthly) instead of 40000 (Whales monthly).

So the bug is: **the invoice object in the webhook does not provide `subscription` (or we read it wrong), so we never get `sub_id`, and we never use subscription metadata for plan/interval.**

## Fix strategy

1. **Resolve `sub_id` when missing from payload**  
   When `data.get("subscription")` is None or empty, retrieve the invoice by `data.get("id")` and read `subscription` from the retrieved object (optionally with `expand=["subscription"]`). Normalize to a string subscription ID and use it for the rest of the handler.

2. **Keep existing fallback**  
   Once `sub_id` is set (from payload or from retrieved invoice), the existing logic that uses `stripe.Subscription.retrieve(sub_id)` and `metadata.plan` / `metadata.interval` will run, so we award Whales tokens when the checkout was for Whales.

3. **Optional: prefer subscription metadata for plan when we have sub_id**  
   We can also use subscription metadata as the primary source for plan/interval when `sub_id` is present (our checkout always sets it), and only fall back to invoice line items when subscription metadata is missing. This makes behavior robust even if invoice line structure changes.

## Implementation steps

1. **Normalize `sub_id` from payload**  
   - `sub_id_raw = data.get("subscription")`  
   - If string (and non-empty): `sub_id = sub_id_raw.strip()`  
   - If dict: `sub_id = sub_id_raw.get("id")`  
   - Else: `sub_id = None`

2. **Retrieve invoice when `sub_id` is None**  
   - If `sub_id` is None/empty and `data.get("id")`:  
     - `inv = stripe.Invoice.retrieve(data["id"], expand=["subscription"])`  
     - `sub_raw = inv.get("subscription")` or getattr  
     - If string: `sub_id = sub_raw`; if dict: `sub_id = sub_raw.get("id")`; else keep None.  
   - Log when we resolve `sub_id` via retrieve so we can see it in debug logs.

3. **Use subscription metadata for plan/interval when we have sub_id**  
   - When `sub_id` is present, after (or instead of) calling `_plan_interval_from_invoice(data)`, fetch subscription (reuse `sub_for_metadata` if already fetched) and read `metadata.plan` and `metadata.interval`.  
   - If both are valid (e.g. plan in ("pro","ai_ultra","whales") and interval in ("monthly","yearly")), use them; otherwise keep result from invoice line items.

4. **Add debug logging**  
   - Log when `sub_id` was missing in payload and was set from retrieved invoice.  
   - Log when plan/interval is taken from subscription metadata.

## Files to change

- `main.py`: invoice.payment_succeeded block (sub_id resolution, optional plan/interval from sub metadata first, logging).

## Non-goals

- No change to checkout session creation (metadata already correct).
- No change to token amounts or idempotency logic.
- No change to other webhook events.
