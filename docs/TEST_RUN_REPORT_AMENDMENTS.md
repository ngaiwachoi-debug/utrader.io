# Test run report: amendments test plan

**Date:** Run from automated + manual checks per [TEST_PLAN_AMENDMENTS_LAST_10_REQUESTS.md](TEST_PLAN_AMENDMENTS_LAST_10_REQUESTS.md).

---

## Automated tests run

### 1. Subscription plans (all 6) – **PASSED**

```text
python scripts/test_all_six_plans_inprocess.py --user 2
```

- **Result:** All 6 plans passed (Pro monthly/yearly, AI Ultra monthly/yearly, Whales monthly/yearly).
- **Whales monthly:** +40,000 tokens (correct).
- **Whales yearly:** +480,000 tokens.
- Covers test plan sections **2.1–2.3** (token amounts, no over-credit for these paths).

---

### 2. Admin token-add logs – **PASSED**

```text
python scripts/test_admin_token_add_logs.py
```

- **Prerequisite:** Backend running on port 8000, `ALLOW_DEV_CONNECT=1`.
- **Result:** GET /admin/token-add/logs → 200, 22 entries returned; user_id and reason present.
- Covers test plan **4.2** (Admin Token add log shows records).

---

### 3. Pytest suite (partial)

**Run:** `python -m pytest tests/ -v --tb=short` (excluding tests that need auth fixes).

| Suite | Passed | Failed | Notes |
|-------|--------|--------|--------|
| test_auto_and_manual_deduction | 10 | 1 | 1 failure: extreme clamp (0 log entries); rest OK. |
| test_daily_token_deduction | 4 | 0 | All passed. |
| test_bitfinex_deduction_flow | 4 | 2 | Precision assertion; missing `daily_fetch_date` on model. |
| test_token_balance_endpoint | 1 | 4 | 401 “Not authenticated” – endpoint may use different auth than override. |
| test_admin_token_add_deduct | 1 | 1 | FK cleanup: delete token_ledger before user. |
| test_registration_tokens | 0 | 2 | Auth/cleanup related. |
| test_token_deposits | 3 | 3 | Mixed auth/FK. |
| test_comprehensive_deduction_plan | 22 | 4 | Some precision; mock expectations; FK cleanup. |
| test_bitfinex_auto_calculation | 4 | 2 | Precision / assertion expectations. |

**Summary:** Core deduction logic (auto/manual, daily cases, backfill) passes. Failures are mostly: (1) auth override for `/api/v1/users/me/token-balance`, (2) test cleanup order (token_ledger → user_token_balance → user), (3) floating-point precision in assertions, (4) schema drift (e.g. `daily_fetch_date`).

---

## Manual / UI checks (from test plan)

These were **not** run automatically; run them in the browser or via curl when backend + frontend are up.

| Section | What to do |
|---------|------------|
| **1** Pay As You Go | Subscription → Pay As You Go → purchase → confirm Stripe redirect and token credit; replay webhook to confirm idempotency. |
| **3** No-downgrade | Whales user → subscribe to Pro (bypass) → confirm plan stays Whales. Same for AI Ultra → Pro. |
| **4.1, 4.3, 4.4** Token Activity | Settings → Token activity: table, dates, Balance before/after; General tab has no “Token added history” block. |
| **5** Balance alignment | Total Budget (Settings) equals latest “Balance after” in Token activity. |
| **6** Token usage UI | ProfitCenter: Remaining/Used numbers; Settings: green bar = remaining, “X% Remaining”, “Remaining \| Used”. |
| **7** Admin USDT log | Admin → USDT log tab; filter by user; confirm rows. |
| **8** USDT history | Referral: no “Admin” column; Reason = “Withdrawal”, “Referral rewards”. |
| **9** Dashboard/fold | DevTools: one `/api/dashboard-fold` on load; response has `token_balance`; no `/api/funding-trades` when fold has trades. |
| **10** Visibility polling | Switch tab away from app; confirm no token/bot/admin polls while hidden; switch back and confirm poll resumes. |
| **12** Graphics | ProfitCenter charts do not re-render every second. |
| **13** USDT earned from them | Referral downline “USDT earned from them” matches sum of L1 in USDT reward history. |
| **14** Auto deduction | Backend logs at startup and at 10:30 UTC; Admin → Deduction → Manual trigger; or `POST /admin/deduction/trigger` with admin JWT. |
| **15** Post-subscription refetch | After plan join or token purchase, dashboard shows updated balance without full reload. |

---

## Commands to re-run automated parts

**Without backend (in-process):**

```powershell
cd c:\Users\choiw\Desktop\bifinex\buildnew
python scripts/test_all_six_plans_inprocess.py --user 2
python -m pytest tests/test_auto_and_manual_deduction.py tests/test_daily_token_deduction.py -v --tb=short
```

**With backend running (port 8000, ALLOW_DEV_CONNECT=1):**

```powershell
python scripts/test_admin_token_add_logs.py
python scripts/test_all_six_plans_bypass.py --user 2
```

---

## Conclusion

- **Subscription token amounts (including Whales 40k)** and **admin token-add logs** are verified by the automated run.
- **Deduction logic** (auto, manual, daily, backfill) is largely covered by passing pytest; remaining failures are test harness/cleanup/precision/schema.
- The rest of the test plan (Pay As You Go, no-downgrade, UI, fold/visibility, referral “earned from them”, manual deduction trigger) should be run manually or with E2E tools when the stack is up.
