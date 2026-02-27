# Admin Panel – Validation Checklist

Use this checklist to confirm all admin features work as intended.

| # | Item | How to verify |
|---|------|----------------|
| 1 | **Admin email redirect** | Log in with `ngaiwanchoi@gmail.com` (or your `ADMIN_EMAIL`). You must be redirected to `/admin` (admin panel), not `/dashboard`. |
| 2 | **Non-admin redirect** | Log in with another Gmail account. You must be redirected to `/dashboard`, not `/admin`. |
| 3 | **Gmail-only login** | Non-Gmail login is blocked (Access Denied). Only Google OAuth is available. |
| 4 | **Admin panel access** | With admin account, open `/admin`. Panel loads with sidebar (Users, API Keys, Bot Control, Deduction, USDT Credit, Withdrawals, Referrals, Notifications, Settings, Health, API Failures, Audit Logs). |
| 5 | **403 for non-admin** | While signed in as a non-admin user, open `/admin`. Either “Not authorized” is shown or API calls return 403. |
| 6 | **User list and edit** | In Users section: list loads; search filters by email/plan/bot; changing plan tier updates the user; setting “Tokens” and blurring updates `tokens_remaining`. |
| 7 | **Export CSV** | Click “Export CSV” in Users section. A CSV file downloads with columns id, email, plan_tier, etc. |
| 8 | **Bot control** | In Bot Control: Start/Stop for a user changes bot state; “Load logs” for a user ID shows terminal log lines (or empty). |
| 9 | **Deduction** | In Deduction: “Manual trigger” runs deduction and new entries appear in the table; Rollback with valid user_id and date (YYYY-MM-DD) adds tokens back. |
| 10 | **Audit logs** | Audit section shows entries; filter by action/email; Export CSV downloads audit_logs.csv. |
| 11 | **API Keys** | API Keys section lists users with masked key (first 4 + last 4); Reset clears keys (confirm). |
| 12 | **Bulk token** | In Users, Bulk token adjustment: enter `user_id,amount` lines, Apply; success/failed count shown. |
| 13 | **Subscriptions / Plan** | Set plan and extend expiry via user detail or PATCH /admin/users/{id}; GET /admin/subscriptions lists users. |
| 14 | **USDT Credit** | USDT Credit section lists balances; user detail page allows Adjust (+/- amount). |
| 15 | **Withdrawals** | Withdrawals section lists requests; filter by status; Approve/Reject for pending. User can create via POST /api/v1/withdrawal-request. |
| 16 | **Referrals** | Referrals section shows user, referrer, downlines; user detail shows referral tree. |
| 17 | **Notifications** | Send notification (title, content, optional target user); list of sent notifications. |
| 18 | **Settings** | Settings section shows platform variables; Save updates DB (registration bonus, min withdrawal, etc.). |
| 19 | **User detail page** | Click View on a user or go to `/admin/users/{user_id}`. Overview shows profile, tokens, USDT, API key, referrals, withdrawals, deduction history, audit; quick actions: set tokens, adjust USDT, reset API key. |

All items should pass for the admin panel to be considered production-ready.
