# Leaderboard and Top Referral Gain Plan

## Overview

- **Leaderboard** (existing): Top 100 by yield; Gmail-style emails; obfuscated display; refreshed daily after 10:00 UTC profit run.
- **Top referral gain** (new): One additional tab on top of the Leaderboard page. Same pattern: 100 users, random dataset generated after daily profit calculation, same email blurring (first 3 chars + ***@gmail.com). USDT gain 500–10,000 daily, ranked by top gainer. Auto-generate runs in the same daily job as the ranking snapshot.

## 1. Backend: referral_gain_snapshot

- **Migration**: `migrations/add_referral_gain_snapshot.sql` – table `referral_gain_snapshot` with `rank` (PK), `user_display`, `usdt_gain_daily`, `updated_at`.
- **Model**: `ReferralGainSnapshot` in `models.py` (same style as `RankingSnapshot`).
- **Refresh**: `_refresh_referral_gain_snapshot(db)` – 100 rows, `user_display` via `_random_gmail_display(rng)` (same as ranking), `usdt_gain_daily` uniform 500–10,000, sort by `usdt_gain_daily` desc, assign rank 1–100. Date-seeded for stable daily data.
- **API**: `GET /api/referral-gain?page=1&per_page=10` – paginated, same shape as ranking (items, total, page, per_page). Optional `POST /api/referral-gain/refresh` (dev-only, same as ranking refresh).

## 2. Daily and startup integration

- In `_run_daily_gross_profit_scheduler()`, after `_refresh_ranking_snapshot(db_rank)`, call `_refresh_referral_gain_snapshot(db_rank)` (reuse same DB session or new one).
- On startup (where ranking_snapshot is seeded if empty), also seed `referral_gain_snapshot` if empty so the tab has data before the first 10:00 run.

## 3. Frontend: Leaderboard page tabs

- **Tabs**: On the Leaderboard page, add two tabs at the top: **Yield Leaderboard** (current content) and **Top referral gain**.
- **Top referral gain tab**: Fetches `GET /api/referral-gain?page=&per_page=10`. Table columns: Rank, Trader (obfuscated: first 3 + ***@gmail.com), USDT gain (daily). 10 per page, 10 pages. Client-side fallback: if API returns empty, generate 100 fake rows (same Gmail-style emails, usdt 500–10,000, date-seeded) so the UI always shows data.

## 4. Testing auto-generate

- **Seed script**: Add `scripts/seed_referral_gain_snapshot.py` (or extend seed script) to run migration and `_refresh_referral_gain_snapshot` so referral_gain_snapshot can be populated manually.
- **Dev refresh**: Call `POST /api/referral-gain/refresh` (when `ALLOW_DEV_CONNECT=1`) to regenerate and verify.
- **Daily run**: Confirm that after the 10:00 UTC profit run, both `ranking_snapshot` and `referral_gain_snapshot` are refreshed (logs or DB check).

## Files to add/change

| Area        | File | Change |
|------------|------|--------|
| Migration  | `migrations/add_referral_gain_snapshot.sql` | New table `referral_gain_snapshot`. |
| Backend    | `models.py` | New model `ReferralGainSnapshot`. |
| Backend    | `main.py` | `_refresh_referral_gain_snapshot`, call after ranking refresh in daily run and startup seed; `GET /api/referral-gain`, `POST /api/referral-gain/refresh`. |
| Frontend   | `frontend/components/dashboard/ranking.tsx` | Tabs "Yield Leaderboard" / "Top referral gain"; fetch referral-gain API; table with obfuscated email and USDT gain; fallback generator. |
| Script     | `scripts/seed_referral_gain_snapshot.py` | Optional; run migration + refresh for referral_gain_snapshot. |
