# Mobile (iPhone) responsiveness refinement plan

## Problem

- **Bottom nav**: Fixed at `bottom-0` with no safe-area insets. On iPhone X and later, the home indicator and system gestures sit at the very bottom; content and nav buttons can be obscured or hard to tap.
- **“On tab, user won’t be able to see”**: When tapping **Terminal** (or other tabs), the main content can sit behind the fixed nav or extend under the safe area, so the user can’t see the full Terminal view (or other pages).
- **Cramped nav**: 8 items in one row with `justify-around` on a narrow iPhone (e.g. 375px) makes small touch targets and cramped labels.
- **Viewport height**: `min-h-screen` (100vh) on iOS is affected by the dynamic browser chrome (address bar); content can be cut off or jump when the UI shows/hides.

## Goals

1. Content never hidden behind the bottom nav or the iPhone home indicator.
2. Bottom nav always above the safe area and with adequate touch targets.
3. Stable, predictable layout on latest iPhones (notch/Dynamic Island and bottom safe area).
4. When switching to Terminal (or any tab), the visible area shows the page content, not empty space or nav overlap.

---

## 1. Safe area insets (critical)

**Where:** Dashboard layout and MobileNav in `frontend/app/[locale]/dashboard/page.tsx`; optional global support in `frontend/app/globals.css` or layout.

**Changes:**

- **Bottom nav**
  - Add bottom padding so the nav sits **above** the home indicator:
    - e.g. `pb-[env(safe-area-inset-bottom)]` on the `<nav>` (and keep `py-2` for top padding), or use a wrapper that adds `padding-bottom: env(safe-area-inset-bottom)`.
  - So the nav bar’s tap area and content are fully in the safe area.

- **Main content**
  - Reserve space at the bottom so scrollable content doesn’t sit under the nav or the safe area:
    - Today: `main` has `pb-20 md:pb-4` (80px on mobile).
    - Change to: use a bottom offset that includes both the **nav height** and **safe area**, e.g. `pb-[5rem+env(safe-area-inset-bottom)]` or a fixed value that’s at least nav height + ~34px (typical iPhone bottom inset), e.g. `pb-24` or `pb-[max(5rem,5rem+env(safe-area-inset-bottom))]` so content never scrolls under the bar.
  - Tailwind doesn’t support `env()` in arbitrary values by default; options:
    - Add a small CSS class in `globals.css`, e.g. `.mobile-main-bottom { padding-bottom: max(5rem, 5rem + env(safe-area-inset-bottom)); }` and use it on `<main>` for mobile only, or
    - Use inline style for the mobile case, or
    - Use Tailwind’s `safe-area-inset-*` if available in your stack; otherwise the class above is the most reliable.

**Outcome:** Nav is above the home indicator; main content has enough bottom padding so that when the user scrolls or switches to Terminal, the last part of the content is visible above the nav.

---

## 2. Viewport and page height (recommended)

**Where:** Root or locale layout viewport export; dashboard wrapper and main.

**Changes:**

- **Viewport meta (Next.js `viewport` export)**  
  In `app/layout.tsx` or `app/[locale]/layout.tsx`, set:
  - `viewportFit: "cover"`  
  so iOS uses the full screen and `env(safe-area-inset-*)` is meaningful. You can keep `themeColor` as is.

- **Page height**
  - Replace `min-h-screen` on the dashboard wrapper with `min-h-[100dvh]` (or `min-h-svh` if you have it) so the initial height matches the visible viewport on iOS and doesn’t jump when the address bar hides. If `100dvh` isn’t in your Tailwind config, add it or use `min-h-[100dvh]` via arbitrary value.
  - Ensure the main content area is scrollable (e.g. `overflow-y-auto` or default document scroll) and that the only fixed element is the bottom nav, so the “visible” area is always the viewport minus header and nav.

**Outcome:** No layout jump from 100vh on iOS; safe areas apply correctly; one clear scroll region.

---

## 3. Bottom nav layout and touch targets (recommended)

**Where:** `MobileNav` in `frontend/app/[locale]/dashboard/page.tsx`.

**Current:** 8 items in one row, `justify-around`, `px-3 py-1.5`, `text-xs`. On a narrow iPhone this yields small tap areas and the “Terminal” (or last) button can be near the edge.

**Options (pick one or combine):**

- **A. Horizontal scroll**
  - Make the nav a horizontally scrollable row (`overflow-x-auto`, `flex-nowrap`, `gap-2`, hide scrollbar with `scrollbar-hide` or similar) so all 8 items stay in one row but the user can scroll to reach Terminal/Settings. Ensure the first few items are visible by default.
  - Add `padding-left` / `padding-right` with `env(safe-area-inset-left)` and `env(safe-area-inset-right)` if you want the nav to respect side notches (e.g. landscape).

- **B. “More” menu**
  - Show 4–5 primary items (e.g. Profit, Live, Market, ROI, Subscription) and put the rest (Referral, Terminal, Settings) in a “More” button that opens a bottom sheet or dropdown. Reduces crowding and keeps touch targets larger.

- **C. Two rows**
  - Two rows of 4 items each. Slightly taller nav but each button is larger and easier to tap.

**Touch targets:**

- Use a minimum height of **44px** for each nav button (Apple HIG): e.g. `min-h-[44px]` and `min-w-[44px]` (or adequate padding) so each icon+label is at least 44pt. Increase padding if needed (e.g. `py-2.5` or `py-3`).

**Outcome:** “Terminal” and other tabs are reachable and tappable; labels aren’t clipped; nav doesn’t feel cramped.

---

## 4. Terminal tab: ensure content is visible (recommended)

**Where:** Dashboard layout and optionally `TerminalView`.

**Issue:** When the user taps “Terminal”, the new content may not scroll to top, or the visible area might be the bottom of the previous page, so it looks like “nothing is visible”.

**Changes:**

- When `activePage` changes (e.g. to `"terminal"`), scroll the main content (or window) to top so the user sees the Terminal content immediately. Options:
  - Use a `ref` on `<main>` and call `mainRef.current?.scrollTo(0, 0)` when `activePage` changes, or
  - Use `window.scrollTo(0, 0)` in a `useEffect` that depends on `activePage`.
- Ensure the main content has enough bottom padding (from step 1) so when the user scrolls to the bottom of the Terminal view, the last line is still above the bottom nav.

**Outcome:** Switching to Terminal (or any tab) shows the top of that page; full content is scrollable and not hidden behind the nav.

---

## 5. Optional: global safe-area utilities

**Where:** `frontend/app/globals.css`.

**Changes:**

- Add utility classes or variables for safe areas so other mobile screens can reuse them, e.g.:
  - `.pb-safe` = `padding-bottom: env(safe-area-inset-bottom);`
  - `.pt-safe` = `padding-top: env(safe-area-inset-top);`
- Use these on the dashboard and any other full-screen mobile layout (e.g. admin-login, landing) so fixed bars or key actions stay in the safe area.

**Outcome:** Consistent handling of notches and home indicator across the app.

---

## Implementation order

1. **Safe area for nav + main (step 1)** – Fixes “can’t see content” and nav overlapping home indicator.
2. **Scroll to top on tab change (step 4)** – Fixes “on tab, user won’t be able to see” for Terminal and other tabs.
3. **Viewport + min-height (step 2)** – Stabilizes layout on iOS.
4. **Nav layout and touch targets (step 3)** – Improves usability and reachability of Terminal and other items.
5. **Global safe-area utilities (step 5)** – Optional; use when you add or refine other mobile pages.

---

## Files to touch

| File | Changes |
|------|--------|
| `frontend/app/[locale]/dashboard/page.tsx` | Nav: safe-area bottom padding. Main: bottom padding including safe area. Optional: scroll-to-top on `activePage` change; MobileNav layout (scroll / More / two rows) and 44px touch targets. |
| `frontend/app/layout.tsx` or `app/[locale]/layout.tsx` | Viewport: `viewportFit: "cover"`. |
| `frontend/app/globals.css` | Optional: `.pb-safe`, `.pt-safe`, or a class for main bottom padding; add `min-h-dvh` if not in Tailwind. |
| `tailwind.config.*` | If needed: extend with `minHeight: { dvh: '100dvh' }` or use arbitrary value `min-h-[100dvh]` in dashboard. |

---

## Testing

- **Devices:** iPhone SE (small), iPhone 15/16 (Dynamic Island, standard bottom inset), iPhone 15/16 Pro Max (large).
- **Safari iOS:** Check with address bar visible and after scrolling (bar hidden) to confirm no jump and no content under nav/safe area.
- **Flow:** Open dashboard → tap Terminal → confirm Terminal content is visible and scrollable to the end; tap other tabs and confirm the same; rotate to landscape if the nav is visible and confirm safe areas and tap targets.
