# Bot available balance vs w[4] and idle error fix

## 1. Aligning bot with check script (same value)

The bot (`WallStreet_Omni_FullEngine.deploy_matrix`) and the diagnostic script (`scripts/check_wallet_available_user2.py`) must use the **same** available balance so that:

- When the script says "Create orders? YES", the bot deploys.
- When the script says "Create orders? NO", the bot skips deploy and we see why in logs.

### 1.1 Formula (same in both)

- **w[2]** = total balance (funding wallet).
- **w[4]** = Bitfinex AVAILABLE_BALANCE (can be null or 0).
- **in_offers** = sum of amounts in `/auth/r/funding/offers` for that currency (fUSD → USD, fUST → UST).
- **Available**:
  - If **w[4]** is not null and **w[4] ≥ MIN_ORDER_AMT** (150 for USD/UST): **available = w[4]**.
  - Else: **available = max(0, balance − in_offers)**.

### 1.2 Changes made in the bot

1. **Wallet row match (robust)**  
   Bitfinex can return `w[1]` as "UST" or "USDT" for the same wallet. The bot now treats UST/USDT/USDt as one currency when resolving the funding wallet row (so it always finds the same row the check script would use).

2. **Diagnostic logging**  
   - When using **w[4]**: log  
     `[currency] Available = w[4] = X (same as check script)`.  
   - When using **balance − offers**: log  
     `[currency] API available=0/null; using balance - offers = X (w[2]=... in_offers=...)`.  
   - When **skipping deploy** (available &lt; MIN): log  
     `[currency] Idle/skip: w[2]=... w[4]=... in_offers=... available=... MIN=... (compare with scripts/check_wallet_available_user2.py)`.

3. **Same logic as check script**  
   No change to the formula; only matching and logging were updated so the bot’s “available” is the same as the script’s “Bot available” and we can compare them in logs.

## 2. Idle error: bot skips deploy but script says create orders

**Symptom:** Terminal shows “Idle” or no “Deploying” / “Grid Available”, while `check_wallet_available_user2.py` shows “Create orders? YES” and a correct available balance.

**Causes and fixes:**

| Cause | Fix |
|-------|-----|
| **Wallet row not found** (e.g. Bitfinex returns "USDT", bot expected "UST") | Done: bot now matches UST/USDT/USDt so the same wallet row is used as in the script. |
| **Different API response** (e.g. bot sees w[4]=0 or null) | Compare bot’s new “Idle/skip” log with script output for the same moment. If w[4] in script is non-null and ≥150 but bot logs w[4]=0 or null, investigate auth or endpoint (same user/keys, same `/auth/r/wallets`). |
| **in_offers mismatch** (bot uses per-symbol offers, script uses all then aggregates) | Bot uses `/auth/r/funding/offers/{symbol}` (e.g. fUSD). Script uses `/auth/r/funding/offers` and aggregates by currency. Totals should match; if not, check symbol normalization (fUSD→USD, fUST→UST) in script and bot. |
| **MIN_ORDER_AMT / spot_price** | For USD/UST, MIN_ORDER_AMT = 150. If the engine was built with a different currency or spot_price, MIN could be wrong. Idle/skip log prints MIN so you can confirm. |

## 3. How to verify “same value”

1. Run the check script (same user as bot):  
   `python scripts/check_wallet_available_user2.py`
2. Note for USD and USDT: **BALANCE w[2]**, **AVAILABLE w[4]**, **In offers**, **Bot available**, **Create orders?**
3. Restart the bot (or wait for the next deploy_matrix run).
4. In the bot terminal, look for either:
   - `[USD] Available = w[4] = X (same as check script)` and `[USD] Grid Available: X`, or  
   - `[USD] Idle/skip: w[2]=... w[4]=... in_offers=... available=... MIN=...`
5. Compare:
   - Bot’s **w[2]** and **w[4]** and **in_offers** and **available** should match the script’s **BALANCE w[2]**, **AVAILABLE w[4]**, **In offers**, **Bot available**.
   - If they match but script says “Create orders? YES” and bot still logs “Idle/skip”, then **available** in the bot is &lt; MIN (check MIN in the log). If they don’t match, use the idle/skip line to see which of w[2], w[4], or in_offers differs and fix that path (wallet match, offers aggregation, or API).

## 4. Summary

- Bot and `check_wallet_available_user2.py` now use the **same** available rule and the bot logs the numbers it uses.
- **Robust wallet match** for UST/USDT avoids “wallet not found” and wrong balance/available.
- **Idle/skip log** explains every “no deploy” with w[2], w[4], in_offers, available, and MIN so you can align with the script and fix any remaining idle error.
