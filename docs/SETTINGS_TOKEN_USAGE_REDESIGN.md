# Settings Page Redesign – Token Usage (Production-Ready)

## 1) Full Code Locations

- **Settings page:** `frontend/components/dashboard/settings.tsx` (full copy-pasteable; all imports, state, API calls, JSX).
- **Helpers:** `frontend/lib/calculateTokenUsage.ts` with:
  - `calculateTotalBudget(purchasedTokens: number): number`
  - `calculateUsedTokens(totalBudget: number, remaining: number): number`
  - `calculateUsagePercentage(used: number, total: number): number`
  - `formatRenewalDate(expiry: string | null): string`
- **Backend:** `main.py` – `UserStatusResponse` includes `pro_expiry` (ISO string); `/user-status/{user_id}` returns it for "Next Renewal Date".

Key changes in code (commented in `settings.tsx`):
- Replaced "Lending Usage" with "Token Usage" section; progress bar uses `/api/v1/users/me/token-balance`.
- Removed Lending Limit section, Custom Lending Limit toggle, and all Lending Strategy/APY/Tier UI.
- Account & Membership card restructured: Current Plan, Rebalancing Frequency (hardcoded "Every 30 minutes"), Token Usage %, Tokens Remaining, Next Renewal Date.
- First tab renamed to "General"; content is General Settings only (Base Currency, Time Zone, Dark Mode). Bot Start/Stop remain in API Keys tab flow; no changes to API Keys, Notifications, Community.

---

## 2) Helper Functions (New File)

File: `frontend/lib/calculateTokenUsage.ts`

- `calculateTotalBudget(purchasedTokens)` → `purchasedTokens + 150` (registration bonus).
- `calculateUsedTokens(totalBudget, remaining)` → `max(0, totalBudget - remaining)`.
- `calculateUsagePercentage(used, total)` → `(used / total) * 100` capped 0–100.
- `formatRenewalDate(expiry)` → `"MMM DD, YYYY"` in local time, or `"No renewal date (Free Plan)"` if null.

---

## 3) UI Mockups (Text-Based) & Removed Elements

### Before–After (ASCII)

**BEFORE (conceptual):**
```
+------------------------------------------------------------------+
| Account & Membership                                             |
| [Avatar] User Name  [Trial User]                                 |
| Trial Plan · user@email.com                                      |
|                                                                  |
| Lending Limit    Rebalancing     Token usage    Tokens remaining |
| $250,000         Every 3 min     X tokens used  Y tokens          |
|                                                                  |
| Lending Usage                                                    |
| [=================>                    ] 45%                     |
| $used                    $lending_limit                           |
+------------------------------------------------------------------+
| [Lending] [Notifications] [API Keys] [Community]                 |
| Lending Configuration                                            |
| Enable Lending [toggle]  Custom Lending Limit [toggle]            |
| General Settings: Base Currency, Time Zone, Dark Mode             |
+------------------------------------------------------------------+
```

**AFTER (redesigned):**
```
+------------------------------------------------------------------+
| Account & Membership                                             |
| [Avatar] User Name  [Trial User]                                 |
| Trial Plan · user@email.com                                      |
|                                                                  |
| Current Plan   Rebalancing Freq   Token Usage   Tokens Remaining  Next Renewal |
| Trial Plan     Every 30 minutes   25% Used      3750 Tokens       Mar 15, 2026 |
|                                                                  |
| Token Usage                                                      |
| [=========>                              ] 25% Used              |
| Tokens Used: 500 | Remaining: 1500        Total Budget: 2000     |
+------------------------------------------------------------------+
| [General] [Notifications] [API Keys] [Community]                  |
| General Settings                                                 |
| Base Currency [USD/USDt]  Time Zone [UTC/...]  Dark Mode [toggle]|
+------------------------------------------------------------------+
```

### Exact Elements Removed (Verification)

| Removed Element | Location (before) |
|-----------------|-------------------|
| Entire "Lending Limit" section | Account card: row with DollarSign icon, "$250,000" and progress based on used_amount/lending_limit |
| Lending Usage progress bar (used_amount / lending_limit) | Replaced by "Token Usage" bar (tokens from /api/v1/users/me/token-balance) |
| "Custom Lending Limit" toggle | Lending tab: "Lending Configuration" → "Custom Lending Limit" |
| "Enable Lending" toggle | Lending tab: "Lending Controls" → "Enable Lending" |
| "Lending Configuration" heading and "Lending Controls" block | First tab content (tab renamed to General; only General Settings kept) |
| Any "Lending Strategy", "Lending APY", "Lending Tier" text/buttons/labels | None were present in original; none added |
| DollarSign icon and lending_limit/used_amount state | Removed from Account card and from component state |

---

## 4) Test Instructions (Step-by-Step)

### Run frontend (local dev)

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:3000` (or the port shown).

### Log in and open Settings

1. Log in (e.g. Google OAuth or dev login).
2. Navigate to **Settings** (sidebar or nav).

### Verify behaviour

1. **Token Usage progress bar**
   - Ensure backend and `/api/v1/users/me/token-balance` are available (JWT).
   - Example: `purchased_tokens = 2000`, registration 150 → total budget 2150; `tokens_remaining = 1650` → used 500 → 500/2150 ≈ 23%.
   - Bar should show ~23% with green segment; label "23% Used"; below: "Tokens Used: 500 | Remaining: 1650" and "Total Budget: 2150".

2. **Lending controls removed**
   - No "Lending Limit" row (no $250,000).
   - First tab is "General" (not "Lending"); no "Enable Lending" or "Custom Lending Limit" toggles.
   - No "Lending Configuration" or "Lending Controls" section.

3. **Account & Membership card**
   - Current Plan: e.g. "Pro Plan" or "Trial Plan".
   - Rebalancing Frequency: "Every 30 minutes".
   - Token Usage: "X% Used" (matches bar).
   - Tokens Remaining: "X Tokens" (from token-balance).
   - Next Renewal Date: "MMM DD, YYYY" or "No renewal date (Free Plan)" if `pro_expiry` is null.

4. **Loading / error states**
   - **Loading:** Token Usage shows a skeleton bar until first token-balance response.
   - **Error:** 401/500/429: message "Failed to load token usage data" or rate limit / contact support (red text). No progress bar in error state.

5. **Bot Start/Stop (no regressions)**
   - API Keys tab: save keys → bot auto-start still triggered.
   - Live Status (or wherever Start/Stop live): Start Bot and Stop Bot still work; no accidental removal of bot controls.

---

## 5) Compatibility Check Report

| Area | Status | Notes |
|------|--------|--------|
| Bot lifecycle (Start/Stop, auto-start, status polling) | No impact | No changes to start-bot/stop-bot or Live Status; API Keys tab still calls start-bot after save. |
| Daily token deduction (API data) | Compatible | Token Usage uses `/api/v1/users/me/token-balance`, which reflects post-deduction `tokens_remaining` and `purchased_tokens`. |
| Existing API calls | Compatible | Still use `getBackendToken()`, `user-status/{userId}` (now with `pro_expiry`), and new `/api/v1/users/me/token-balance`; no breaking changes to other endpoints. |
| Responsive design | Preserved | Same grid/layout patterns and breakpoints (e.g. `sm:grid-cols-2 lg:grid-cols-5`); no new styles. |
| Auth (401) | Handled | Token-balance 401: no redirect in component; existing app auth flow (e.g. session refresh) applies. |
| Rate limit (429) | Handled | User sees "Too many requests – please try again in 1 minute" (i18n key). |
| 500 | Handled | "Failed to load token data – contact support" (i18n). |

---

## 6) Final Validation Checklist

- [ ] **Token Usage header** – Section title is "Token Usage" (exact wording).
- [ ] **Progress bar logic** – Total Budget = purchased_tokens + 150; Tokens Used = Total − tokens_remaining; Usage % = (Used / Total) × 100, cap 100%, floor 0%.
- [ ] **Progress bar visual** – Width 100%, height 8px; gradient 0–50% #10b981, 51–80% #f59e0b, 81–100% #ef4444; centered "{X}% Used"; border-radius 4px.
- [ ] **Labels below bar** – Left: "Tokens Used: X | Remaining: Y"; Right: "Total Budget: Z".
- [ ] **Total Budget = 0** – Bar hidden; centered "No tokens available".
- [ ] **Loading state** – Skeleton loader while fetching token data.
- [ ] **Error state** – Red "Failed to load token usage data" (or 429/500 messages) when API fails.
- [ ] **Lending Limit removed** – No $250,000 or lending limit progress in Account card.
- [ ] **Lending controls removed** – No Custom Lending Limit or Enable Lending toggles; no Lending Strategy/APY/Tier.
- [ ] **Account card fields** – Current Plan, Rebalancing Frequency (Every 30 minutes), Token Usage %, Tokens Remaining, Next Renewal Date (or "No renewal date (Free Plan)"); Bot Start/Stop and API Keys unchanged.
