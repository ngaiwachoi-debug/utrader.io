# Admin Panel Guide – uTrader.io

## 1. Login (Gmail-only)

- **Who can be admin:** Only the email set as `ADMIN_EMAIL` (default `ngaiwanchoi@gmail.com`) can access the admin panel.
- **How to log in:**
  1. Open the app and click **Sign in with Google** (or go to `/login`).
  2. Sign in with the **admin Gmail account**.
  3. You will be **redirected to `/admin`** (admin panel).  
     Other users are redirected to `/dashboard` (user dashboard).
- **Gmail-only:** Login is Google OAuth only. Non-Gmail accounts are blocked (Access Denied).

## 2. Admin panel layout

- **Sidebar:** Users, API Keys, Bot Control, Deduction, USDT Credit, Withdrawals, Referrals, Notifications, Settings, Health, API Failures, Audit Logs.
- **Header:** Admin email and **Sign out**.
- **Main area:** Content for the selected section.

## 3. User management

- **List:** All users with ID, email, plan, tokens remaining, bot status, status.
- **Search:** Use the search box to filter by email, plan tier, or bot status.
- **Edit plan:** Click a plan badge (trial, pro, expert, guru) to set that user’s plan.
- **Edit tokens:** Enter a number in the “Tokens” field and blur (or press Enter) to set `tokens_remaining` for that user.
- **Export CSV:** Click **Export CSV** to download a CSV of all users.
- **Bulk token adjustment:** In the "Bulk token adjustment" card, enter lines like `user_id,amount` (e.g. `5,100`) and click **Apply** to add tokens to multiple users.
- **User detail:** Click **View** or the user email to open `/admin/users/{user_id}` with full overview and quick actions (edit tokens, adjust USDT, reset API key).

## 4. API Keys (sidebar)

- **List:** User ID, email, status (Set / Not set), masked key (first 4 + last 4 chars), last tested.
- **View:** Masked key only; API secret is never exposed.
- **Reset:** Click **Reset** (with confirmation) to clear the user’s API keys; they must reconnect.

## 5. Bot control

- **Start / Stop:** In the table, use **Start** or **Stop** to start or stop the bot for that user.
- **Bot logs:** Enter a **User ID** and click **Load logs** to view terminal logs for that user’s bot.

## 6. Token deduction

- **Manual trigger:** Click **Manual trigger** to run the daily token deduction once (same logic as the 10:15 UTC job).
- **Logs:** The table shows recent deduction log entries (user, time, amount deducted, balance after).
- **Rollback:** Enter **User ID** and **Date** (YYYY-MM-DD) and click **Rollback** to add back the tokens that were deducted for that user on that date (based on in-memory deduction log).

## 7. USDT Credit (sidebar)

- **List:** User, email, balance, total earned, total withdrawn.
- **Adjust:** Open the user’s detail page (`View / Adjust`) to add or deduct USDT credit; all adjustments are logged and appear in USDT history.

## 8. Withdrawals (sidebar)

- **List:** ID, user, amount, address, status (pending / approved / rejected), created, processed.
- **Filter:** All, Pending, Approved, Rejected.
- **Approve:** Deducts `usdt_credit`, marks request approved, records processed time.
- **Reject:** Marks rejected; balance is not deducted. Users submit requests via `POST /api/v1/withdrawal-request`.

## 9. Referrals (sidebar)

- **List:** User, referrer, downline count, referral earnings.
- **View tree:** Click **View tree** (or open user detail) to see level 1/2/3 upline and downline count.

## 10. Notifications (sidebar)

- **Send:** Title, content, optional target user ID (empty = all users). Type: info.
- **List:** Sent notifications with title, type, target, created time.

## 11. Settings (sidebar)

- **Fields:** Registration bonus tokens, min withdrawal USDT, daily deduction UTC hour, bot auto-start, referral system enabled, withdrawal enabled, maintenance mode.
- **Save:** Updates stored in DB; used by the app (e.g. withdrawal_enabled gates `POST /api/v1/withdrawal-request`).

## 12. System health

- **Redis / DB:** Shows whether Redis and the database are reachable (ok or error).

## 13. API failures

- **List:** Recent API failures (e.g. daily refresh, Bitfinex errors) with time, context, user, and error message.
- **Retry:** Use **Retry** on a row to retry the gross profit refresh for that failure/user.

## 14. Audit logs

- **Backend:** `GET /admin/audit-logs` supports filters: `action`, `email`, `start_date`, `end_date`, `limit`.  
  Logs are stored in the database (table `admin_audit_log`); in-memory fallback if DB is empty.  
  All admin mutations are recorded; no delete.
- **Export CSV:** Use the **Export CSV** button; optional filters apply to the export.

## 15. User detail page (`/admin/users/{user_id}`)

- **Profile:** Email, plan, status, bot status, pro expiry, created, referral code, referred by.
- **Token balance:** Remaining, purchased, last gross used; **Apply** to set tokens.
- **USDT Credit:** Balance, earned, withdrawn; **Adjust** to add or deduct.
- **API key:** Status; **Reset keys** to clear.
- **Referral:** Referrer, downline count.
- **Withdrawals:** Table of requests for this user.
- **Deduction history:** Recent deduction rows.
- **Audit entries:** Admin actions that mention this user.

## 16. Troubleshooting

| Issue | What to check |
|-------|----------------|
| Admin panel not loading | Ensure you’re signed in with the admin Gmail. Set `NEXT_PUBLIC_ADMIN_EMAIL` (frontend) and `ADMIN_EMAIL` (backend) if you use a different admin email. |
| Redirect to dashboard instead of admin | Backend and frontend must use the same admin email. Default is `ngaiwanchoi@gmail.com`. |
| 403 on admin API | Backend checks `ADMIN_EMAIL`; JWT must contain that email. Log in again with the admin account. |
| Can’t trigger deduction | Call `POST /admin/deduction/trigger` with a valid admin JWT. Check backend logs for errors. |
| Rollback not finding entries | Rollback uses in-memory deduction log. Only runs after at least one deduction (manual or scheduled) in this process; after restart, only new runs are logged. |

## 17. Security

- **Logout after use** when on a shared machine.
- **Do not share** the admin account; only the configured admin email should access the panel.
- **JWT:** Admin uses the same JWT as users (from NextAuth); backend restricts `/admin/*` to the admin email only.
