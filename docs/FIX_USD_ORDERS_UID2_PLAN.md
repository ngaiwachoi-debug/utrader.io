# Plan: Why USD Is Not Creating Orders for User 2 and How to Fix

## 1. Root cause (why USD might not create orders)

The bot uses **PortfolioManager** → **scan_and_launch** → one **WallStreet_Omni_FullEngine** per funding currency. For each currency it:

1. **Scanner (scan_and_launch)**  
   Starts an engine only for wallets with **w[2] (BALANCE) > 0**. So USD gets an engine if the USD funding wallet has a positive balance.

2. **Engine (deploy_matrix)**  
   Fetches `/auth/r/wallets` again and:
   - **w[2]** = total balance  
   - **w[4]** = AVAILABLE_BALANCE (Bitfinex can return `null` or `0` even when balance exists)
   - If **w[4]** is null or &lt; MIN_ORDER_AMT (150 for USD), the bot uses **available = balance − in_offers** (sum of amounts in `/auth/r/funding/offers` for that currency).
   - If **available &lt; MIN_ORDER_AMT** (150 for USD), the engine **returns without placing any orders**.

So USD does not create orders when:

- **A)** **w[4]** is null or 0 and **(balance − in_offers) &lt; 150**  
  → All USD is already in offers or balance is too low.
- **B)** **w[4]** is set but **&lt; 150** and **(balance − in_offers) &lt; 150**  
  → Same as above.
- **C)** Scanner uses **w[2] &gt; 0** but does not use **w[4]**; if the exchange reports **w[4] = 0** and the bot’s fallback **(balance − in_offers)** is wrong (e.g. offers not fetched correctly), available can be 0.
- **D)** **Shared value bug**  
  Bot and dashboard/check script use different logic or different API responses (e.g. one uses w[4], the other uses balance − offers) and disagree on “available” so the bot thinks there is nothing to deploy.

## 2. Diagnostic script (check w[4] and bot logic)

**Script:** `scripts/check_wallet_available_user2.py`

It:

- Fetches **/auth/r/wallets** and **/auth/r/funding/offers** (same as the bot).
- For **USD** and **USDT**:
  - Prints **w[2]** (balance) and **w[4]** (available balance).
  - Computes **in_offers** from funding offers (same aggregation as the bot).
  - Computes **Bot available** =  
    - **w[4]** if w[4] ≥ 150, else  
    - **balance − in_offers**.
  - Prints whether the bot would **create orders** (Bot available ≥ 150).
- Prints raw funding wallet rows so you can confirm w[4] and w[2] from the API.

**Run:**

```bash
python scripts/check_wallet_available_user2.py
```

Use this to confirm:

- Whether **w[4]** for USD (and USDT) is null/0 or &lt; 150.
- Whether **balance − in_offers** matches what you expect.
- Whether the bot and the script see the **same** “available” value (same API, same formula).

## 3. Check if the bot is “sharing the same value”

- **Bot:** Uses `/auth/r/wallets` and `/auth/r/funding/offers`; available = w[4] if valid and ≥ MIN, else balance − sum(offers for that currency).  
- **Check script:** Now uses the same endpoints and the same aggregation for offers and the same MIN_ORDER_USD (150). So they **do** share the same definition of “available” and the same data source.

If the script shows “Create orders? YES” for USD but the bot still does not place USD orders, then the bug is elsewhere (e.g. different code path, different user/keys, or engine not started for USD). If the script shows “Create orders? NO”, then the fix is to increase available (e.g. cancel stale offers or ensure w[4] is correct on the exchange side) or to lower the minimum (not recommended without product agreement).

## 4. Fix plan (concrete steps)

| Step | Action | Purpose |
|------|--------|--------|
| 1 | Run `python scripts/check_wallet_available_user2.py` for uid 2 | See w[2], w[4], in_offers, Bot available, and “Create orders?” for USD and USDT. |
| 2 | If **w[4]** is null/0 for USD | Confirm Bitfinex is not withholding available; use **balance − in_offers** (already the bot fallback). Ensure **offers** are fetched and aggregated per currency (fUSD → USD, fUST → UST) so the fallback is correct. |
| 3 | If **Bot available &lt; 150** for USD | Either (a) cancel some USD offers so more is free, or (b) add more USD funding, or (c) ensure no bug in offer aggregation (e.g. wrong symbol index or wrong currency normalization). |
| 4 | If script says “Create orders? YES” but bot still does not place USD orders | (a) Confirm the **scanner** started an engine for USD (funding wallet with w[2] &gt; 0). (b) Add a log line in the engine for USD: log **available** and **MIN_ORDER_AMT** right before the `if available < self.MIN_ORDER_AMT: return`. (c) Confirm the running task is for user 2 and the same API keys as the script. |
| 5 | Optional: use w[4] more defensively | If Bitfinex often sends w[4] = 0 for USD while balance &gt; 0, always compute **available = balance − in_offers** for USD (or for all) and use that when w[4] is 0 or null, so the bot does not rely on a possibly incorrect w[4]. |
| 6 | Optional: scanner filter by “available” | Today the scanner starts an engine when **w[2] &gt; 0**. You could also require “available” (w[4] or balance − offers) ≥ MIN_ORDER_AMT before starting the engine for that currency, so the bot does not start an engine that will immediately no-op. |

## 5. Summary

- **Why USD might not create orders:** Available (w[4] or balance − in_offers) is below 150 for USD, so the engine exits without placing orders.
- **Diagnostic:** Run `check_wallet_available_user2.py` to see w[4], balance, in_offers, and “Bot available” for USD and USDT, and whether the bot would create orders.
- **Same value:** The script and the bot now use the same API and same formula; if they disagree, the script output will show where (e.g. w[4] vs balance − offers).
- **Fix:** Use the script to confirm the numbers, then either free up USD (cancel offers / add balance), fix offer aggregation, or add logging to see why the engine returns without placing orders when the script says it should.
