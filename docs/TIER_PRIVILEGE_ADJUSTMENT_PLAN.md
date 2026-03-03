# Tier privilege adjustment plan

This document describes how to align **current tier behaviour** with the **Compare plans** table on the Subscription page (see `frontend/components/dashboard/subscription.tsx`).

## Target table (as amended)

| Feature              | Pro Plan | AI Ultra | Whales AI |
|----------------------|----------|----------|-----------|
| Rebalance interval   | 30 min   | 3 min    | 1 min     |
| Token credit         | 2,000    | 9,000    | 40,000    |
| Use Gemini AI        | —        | ✓        | ✓         |
| Trading terminal view| ✓        | ✓        | ✓         |
| General support      | ✓        | ✓        | ✓         |
| Priority support     | —        | —        | ✓         |
| True ROI             | —        | —        | ✓         |

---

## 1. Trading terminal view — all tiers

**Current state:** Terminal is already usable by all tiers. `terminal-view.tsx` uses tier-based poll intervals (trial 4h, pro 5m, ai_ultra 30m, whales 10m); there is no hard “Whales only” gate in the component.

**Actions:**

- **Done:** Compare table updated so Trading terminal view shows ✓ for Pro, AI Ultra, and Whales.
- **Optional:** In i18n, `dashboard.terminalWhalesOnly` and any copy that says “Whales only” for the terminal can be updated or removed so marketing/UI copy does not imply terminal is Whales-only.

---

## 2. General support — all tiers

**Current state:** No code gate; this is a support/process commitment.

**Actions:**

- **Done:** “General support” row added to the Compare table with ✓ for all three tiers.
- No code changes required; ensure support process/documentation states that general support is available to all paid tiers (and trial if applicable).

---

## 3. Priority support — Whales AI only

**Current state:** Table previously showed ✓ for all tiers; it now correctly shows —/—/✓ (Whales only).

**Actions:**

- **Done:** Compare table updated.
- **Process:** Define “priority support” (e.g. dedicated channel, SLA, or queue priority) and restrict it to Whales AI in support workflows/tools. No application code change needed unless you add in-app priority support routing later.

---

## 4. True ROI — Whales AI only

**Current state:**

- **Navigation:** “True ROI” is shown to everyone in the sidebar (`sidebar.tsx`) and mobile menu (`mobile-menu-drawer.tsx`) with no tier check.
- **Page:** `true-roi.tsx` renders full content for all users; no `plan_tier` check.
- **i18n:** `dashboard.trueRoiWhalesOnly` exists for an upgrade message but is not used for gating.

**Actions (implementation plan):**

1. **Sidebar** (`frontend/components/dashboard/sidebar.tsx`)
   - Sidebar already receives `planTier` from the dashboard page.
   - Filter `allNavItems` (or the list used for rendering) so the item with `id: "true-roi"` is only included when `planTier === "whales"` (normalize tier to lowercase for comparison).
   - Result: True ROI link is hidden for non-Whales users.

2. **Mobile menu** (`frontend/components/dashboard/mobile-menu-drawer.tsx`)
   - The drawer does not currently receive `planTier`. Either:
     - Pass `planTier` from the dashboard page into `MobileMenuDrawer`, and filter `DRAWER_NAV_ITEMS` so “true-roi” is only shown when `planTier === "whales"`, or
     - Use the same user-status/context that provides `plan_tier` on the dashboard (e.g. `useUserStatus()` or equivalent) inside the drawer and filter by `plan_tier === "whales"`.
   - Result: True ROI is not shown in the mobile nav for non-Whales.

3. **True ROI page** (`frontend/components/dashboard/true-roi.tsx`)
   - Obtain `plan_tier` (e.g. from existing user-status API or dashboard context). If the dashboard is a single page that switches content by `activePage`, the parent already has `userStatus`; pass `planTier` (or `plan_tier`) into `TrueROI` as a prop.
   - If `plan_tier !== "whales"`:
     - **Option A:** Render an upgrade block instead of the full page (e.g. message using `t("dashboard.trueRoiWhalesOnly")` and a CTA to Subscription/upgrade).
     - **Option B:** Redirect to Subscription (or dashboard home) when non-Whales users land on True ROI (e.g. via `useEffect` and `router.replace`).
   - Result: Non-Whales users cannot use True ROI content even if they open the route directly.

4. **Direct route (if True ROI has its own URL)**
   - If there is a dedicated route (e.g. `/[locale]/dashboard/true-roi`), apply the same `plan_tier === "whales"` check in that route/layout and redirect or show upgrade UI for non-Whales.

**Tier normalization:** Use the same normalization as elsewhere (e.g. `normalizePlanTier` on the dashboard): compare against `"whales"` in lowercase so backend tier values like `"Whales"` or `"whales"` are handled consistently.

---

## Summary checklist

| Item                         | Status / Action                                      |
|------------------------------|------------------------------------------------------|
| Compare table: Terminal ✓✓✓  | Done                                                 |
| Compare table: General support ✓✓✓ | Done                                          |
| Compare table: Priority —/—/✓ | Done                                                 |
| Compare table: True ROI —/—/✓ | Done                                                 |
| Terminal: code already all-tiers | No change; optional copy update                  |
| General support              | Process/docs only                                    |
| Priority support             | Process/docs only                                    |
| True ROI: hide in sidebar    | Implement filter when `planTier !== "whales"`        |
| True ROI: hide in mobile nav | Pass planTier or use user status; filter drawer items|
| True ROI: gate page content  | Add plan_tier check in TrueROI; show upgrade or redirect |

Once the True ROI gating (sidebar, mobile nav, and page) is implemented, behaviour will match the Compare plans table.
