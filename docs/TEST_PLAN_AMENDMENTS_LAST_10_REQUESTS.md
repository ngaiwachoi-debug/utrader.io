# Test plan: amendments from the last 10 requests

This plan covers all functionalities changed or added in the amendments from the last ~10 requests (Pay As You Go, Whales tokens, no-downgrade, token/USDT logs, balance alignment, UI, admin USDT log, performance, fold/ticker/cache, visibility polling, referral “earned from them”, auto deduction).

---

## 1. Pay As You Go (token top-up)

**Scope:** Subscription page “Pay As You Go” uses Stripe Checkout and same token-adding path as plan joins; idempotency prevents double-credit.

| ID | Test | Steps | Expected |
|----|------|--------|----------|
| 1.1 | Stripe Checkout used | As a user, open Subscription → Pay As You Go, enter amount (e.g. $10), click “Purchase tokens”. | Redirect to Stripe Checkout; after payment success, redirect back with `?tokens=success`. |
| 1.2 | Tokens added | After successful Pay As You Go payment, check dashboard / Settings token balance. | Balance increased by (amount × 100) tokens. |
| 1.3 | Idempotency | Simulate webhook `checkout.session.completed` for same session/one-time token purchase twice (e.g. replay or duplicate event). | Tokens credited only once (second event ignored via idempotency). |
| 1.4 | Token add log | After Pay As You Go purchase, open Settings → Token activity and Admin → Token add log. | One new row: reason deposit/subscription-related, amount = tokens added; Balance before/after present; no Invalid Date. |

---

## 2. Subscription plans (Pro, AI Ultra, Whales) – token amounts

**Scope:** Whales awards 40,000 tokens (not 2,000); no over-crediting (e.g. 160k→320k); correct amounts for all 6 plan/interval combinations.

| ID | Test | Steps | Expected |
|----|------|--------|----------|
| 2.1 | Whales monthly | Subscribe to Whales AI Monthly (e.g. bypass or real Stripe). | Exactly 40,000 tokens added. |
| 2.2 | Whales yearly | Subscribe to Whales Yearly. | Correct token amount per your product config (e.g. 40k or as defined). |
| 2.3 | Pro / AI Ultra | Subscribe to Pro monthly, AI Ultra monthly (separate users or bypass). | Correct token amounts per plan (no double or wrong multiplier). |
| 2.4 | No double-credit | Trigger webhook once for a subscription; check balance and token_ledger. | Single credit; no duplicate ledger rows for same invoice/session. |

---

## 3. No-downgrade plan retention

**Scope:** Higher tier is retained when user “purchases” a lower tier.

| ID | Test | Steps | Expected |
|----|------|--------|----------|
| 3.1 | Whales → Pro | User on Whales subscribes to Pro (bypass or Stripe). | Plan remains Whales (no downgrade). |
| 3.2 | Whales → AI Ultra | User on Whales subscribes to AI Ultra. | Plan remains Whales. |
| 3.3 | AI Ultra → Pro | User on AI Ultra subscribes to Pro. | Plan remains AI Ultra. |
| 3.4 | Pro → Trial/Free | User on Pro does not subscribe to higher; optional test downgrade logic if implemented. | Per product rules (e.g. Pro retained until expiry). |

---

## 4. Token add logs (user and admin)

**Scope:** User Token Activity shows all adds/deductions; Admin Token add log shows records; dates and balance columns correct; no “Token added history” block on Settings General.

| ID | Test | Steps | Expected |
|----|------|--------|----------|
| 4.1 | User Token Activity | As user with token history, open Settings → Token activity tab. | Table shows token add and deduction rows (newest first); dates valid (no “Invalid Date”); columns include Balance before, Balance after. |
| 4.2 | Admin Token add log | As admin, open Admin → Token add log, optionally filter by user. | Table shows rows from token_ledger (subscription, admin, registration, deposit, etc.); no “No token add logs yet” when data exists. |
| 4.3 | Date format | Check any token add row (user or admin). | Date/time parses and displays correctly (e.g. “Mar 5, 2026, 6:33 PM” or configured format). |
| 4.4 | Settings General | Open Settings → General tab. | “Token added history” block is not present (removed from General). |

---

## 5. Balance alignment

**Scope:** “Total Budget” on Settings matches “Balance after” in Token Activity (same source of truth).

| ID | Test | Steps | Expected |
|----|------|--------|----------|
| 5.1 | Same value | Note Total Budget on Settings (token usage card). Open Token activity; note last row “Balance after”. | Total Budget equals the latest “Balance after” (or current balance from same API). |
| 5.2 | After purchase | Add tokens (subscription or Pay As You Go); refresh Settings and Token activity. | Both Total Budget and Balance after reflect the new balance. |

---

## 6. Token usage UI

**Scope:** ProfitCenter shows Remaining/Used numbers; Settings shows green bar = remaining, “X% Remaining”, “Remaining: X | Used: Y”.

| ID | Test | Steps | Expected |
|----|------|--------|----------|
| 6.1 | ProfitCenter numbers | Open dashboard; find Token credit / usage in ProfitCenter. | “Remaining” and “Used” show numeric values next to labels. |
| 6.2 | Settings bar | Open Settings → token usage section. | Green bar represents **remaining** tokens (not used). |
| 6.3 | Settings labels | Check token usage text. | Shows “X% Remaining” and “Remaining: X | Used: Y” (or equivalent). Total Budget displayed. |

---

## 7. Admin USDT log

**Scope:** New admin tab “USDT log” with user filtering.

| ID | Test | Steps | Expected |
|----|------|--------|----------|
| 7.1 | Tab exists | As admin, open Admin panel. | Sidebar/page has “USDT log” (or equivalent) tab. |
| 7.2 | Data and filter | Open USDT log; apply user filter (e.g. user_id or email). | Table shows USDT history (referral earnings, withdrawals, admin adjustments); filtered by selected user. |
| 7.3 | Records | Ensure test user has USDT history (referral reward or withdrawal). | Corresponding rows appear in USDT log when filtered. |

---

## 8. USDT history display (user Referral)

**Scope:** User-facing USDT reward history: no “Admin” column; refined Reason labels.

| ID | Test | Steps | Expected |
|----|------|--------|----------|
| 8.1 | No Admin column | Open Referral / USDT section as user; view “USDT reward history” table. | Table has no “Admin” column. |
| 8.2 | Reason labels | Check Reason column for different types. | “withdrawal” → “Withdrawal”; “referral_earnings_purchase” (or similar) → “Referral rewards”; other reasons human-readable. |

---

## 9. Dashboard load and fold (performance)

**Scope:** Single fold request; token balance and referral bundle; fold fills trades when lending has gross but no trades; no extra `/api/funding-trades` when fold includes trades.

| ID | Test | Steps | Expected |
|----|------|--------|----------|
| 9.1 | One fold on load | Log in; open dashboard; capture network (DevTools). | Initial load uses one `GET /api/dashboard-fold` (plus auth/session). No separate `/api/v1/users/me/token-balance` on first load. |
| 9.2 | Token balance in fold | Inspect `dashboard-fold` response. | Contains `token_balance`: `{ tokens_remaining, total_tokens_added, total_tokens_deducted }`. |
| 9.3 | Referral deferred | Open dashboard (no Referral tab yet). | No request to `/api/v1/user/referral-bundle` until Referral/Settings referral data is needed. |
| 9.4 | Referral bundle single call | Open Referral tab (or section that loads referral data). | One request to `GET /api/v1/user/referral-bundle?limit=50` (not six separate referral endpoints). |
| 9.5 | Fold returns trades | User with gross profit; clear lending cache or use DB/cache path that had no trades. Load dashboard. | Fold response `lending.trades` is non-empty when gross > 0; frontend does not call `GET /api/funding-trades` for that load. |
| 9.6 | Single ticker per fold | Backend: cold cache for both wallets and lending; trigger one `GET /api/dashboard-fold`. | Backend makes one Bitfinex ticker request for the union of currencies (not two separate ticker calls). Check logs or metrics if available. |

---

## 10. Visibility-aware polling

**Scope:** Token balance poll only on Token activity tab and when tab visible; bot status and admin failures poll only when tab visible.

| ID | Test | Steps | Expected |
|----|------|--------|----------|
| 10.1 | Token balance poll | Open Settings; stay on General or API Keys. Wait 60s+. | No repeated token balance refetch (no poll). Switch to Token activity tab; wait. | Refetch runs (e.g. every 60s) while on Token activity. |
| 10.2 | Token poll when hidden | On Token activity tab, switch to another browser tab (dashboard tab hidden). Wait 60s+. | No token balance requests from the hidden tab. Switch back to app tab. | Poll resumes when visible. |
| 10.3 | Bot status poll | Open dashboard (bot status active). Switch to another browser tab for 2+ minutes. | Fewer or no `GET /bot-stats/...` requests while hidden. Switch back. | Poll resumes. |
| 10.4 | Admin failures poll | Open Admin panel; switch to another tab for 1+ minute. | No or paused `GET /admin/api-failures` while hidden. Switch back. | Poll resumes (e.g. every 60s). |

---

## 11. Cache caps (memory/scale)

**Scope:** bitfinex_cache capped at 5000 entries; ticker cache capped at 2000; oldest evicted when over limit.

| ID | Test | Steps | Expected |
|----|------|--------|----------|
| 11.1 | Bitfinex cache cap | (Optional, load test.) Simulate or create > 5000 distinct (user_id, endpoint) cache entries. | Cache size does not grow beyond 5000; oldest entries evicted. |
| 11.2 | Ticker cache cap | (Optional.) Trigger many fold requests with varied currency sets so ticker cache has > 2000 keys. | Ticker cache evicts oldest; size bounded. |

---

## 12. ProfitCenter graphics (no constant refresh)

**Scope:** Charts do not re-render every second due to cooldown timer.

| ID | Test | Steps | Expected |
|----|------|--------|----------|
| 12.1 | Chart stability | Open dashboard; focus ProfitCenter (gross profit / volume chart). Observe for 10–20 seconds. | Chart does not visibly re-render every second; only refresh button cooldown (if any) ticks. |
| 12.2 | Refresh button | Click “Refresh Gross Profit” (or equivalent). | Data refreshes; cooldown shown on button; chart updates once. |

---

## 13. “USDT earned from them” (referral downline)

**Scope:** Referral downline table “USDT earned from them” = L1 from purchases + token burns; matches USDT reward history.

| ID | Test | Steps | Expected |
|----|------|--------|----------|
| 13.1 | Downline amount | User A referred user B. User B makes a purchase or token burn that generates L1 reward for A. Open Referral as user A; check “Referred users” table. | “USDT earned from them” for user B equals sum of L1 rewards from B (purchases + burns). |
| 13.2 | Matches history | Same user A; open “USDT reward history”. | Sum of referral reward entries tied to user B matches “USDT earned from them” for B in the downline table. |

---

## 14. Auto token deduction (logs and manual trigger)

**Scope:** Startup log explains when deduction runs; manual trigger works via Admin or API.

| ID | Test | Steps | Expected |
|----|------|--------|----------|
| 14.1 | Startup log | Restart backend; check logs. | Message: “Auto token deduction runs only at 10:30 UTC when the backend is running. If the server is off at 10:30 UTC, deduction will not run; use Admin Panel → Deduction → Manual trigger or POST /admin/deduction/trigger.” |
| 14.2 | Scheduler log | (If running at 10:30 UTC.) Check logs at 10:30 UTC. | “Daily token deduction: scheduler woke at ~10:30 UTC; starting deduction run.” |
| 14.3 | Manual trigger (UI) | As admin, open Deduction section; click Manual trigger (with optional refresh). | Success; deduction log entries created for users with snapshot data; response or UI shows count/entries. |
| 14.4 | Manual trigger (API) | `POST /admin/deduction/trigger?refresh_first=true` with admin JWT. | 200; body e.g. `{"status":"success","count":N,"entries":[...],"refreshed":M}`. |

---

## 15. Post–subscription / token refetch

**Scope:** After subscription or token purchase success, dashboard refetches user status, wallets, and token balance.

| ID | Test | Steps | Expected |
|----|------|--------|----------|
| 15.1 | After plan join | Complete subscription (e.g. Whales bypass). Return to dashboard. | Token balance and plan tier update without full page reload (refetch user status, wallets, token balance). |
| 15.2 | After Pay As You Go | Complete Pay As You Go; return with `?tokens=success`. | Same refetch; balance reflects new tokens. |

---

## Test execution notes

- **Environment:** Backend, frontend, ARQ worker (if needed for bot), Redis, DB. For Stripe: use test mode and `stripe listen` locally with correct webhook secret in `.env`.
- **Users:** Have at least: one admin, one normal user (e.g. uid 2), one referred user for L1 tests.
- **Order:** Run 1–4 (payments and logs) first; then 5–8 (UI and admin); then 9–12 (performance and polling); then 13–15 (referral and deduction).
- **Regression:** After changes, re-run critical paths: subscription + Pay As You Go (1–2), token add log (4), balance alignment (5), fold and no double funding-trades (9), manual deduction (14).
