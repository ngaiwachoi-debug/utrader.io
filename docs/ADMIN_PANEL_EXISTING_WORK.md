# Admin Panel – Existing Work Audit

## 1. Admin identity and auth

| Item | Status | Details |
|------|--------|---------|
| **Exclusive admin email** | Implemented | Backend `get_admin_user()` uses `ADMIN_EMAIL` env (default **`ngaiwanchoi@gmail.com`**). Set `ADMIN_EMAIL` / `NEXT_PUBLIC_ADMIN_EMAIL` to override. |
| **DB role column** | Not used | `users` table has no `role` column. Admin is determined **only by email** in `get_admin_user()`. |
| **Admin dependency** | Implemented | All `/admin/*` routes use `Depends(get_admin_user)`; non-admin get **403 Forbidden**. |

## 2. Gmail-only login

| Item | Status | Details |
|------|--------|---------|
| **Gmail-only** | Implemented | NextAuth `signIn` callback in `app/api/auth/[...nextauth]/route.ts` returns `true` only when `user.email.endsWith("@gmail.com")`; others get `/?error=AccessDenied`. |
| **Email/password login** | Not present | No email/password provider; only Google OAuth. |

## 3. Admin redirect after login

| Item | Status | Details |
|------|--------|---------|
| **Redirect to /admin for admin** | Implemented | Dashboard page checks session email; if it matches `NEXT_PUBLIC_ADMIN_EMAIL` (default ngaiwanchoi@gmail.com), redirects to `/admin`. |
| **Redirect to /dashboard for others** | Implemented | Login uses `signIn("google", { callbackUrl: "/dashboard" })`; non-admin users stay on dashboard. |
| **Non-Gmail block** | Implemented | Handled by NextAuth `signIn` callback (AccessDenied). |

## 4. Admin panel UI and API

| Item | Status | Details |
|------|--------|---------|
| **Admin page** | Implemented | Uses NextAuth session + `getBackendToken()`; sidebar (Users, Bot Control, Deduction, Health, API Failures, Audit Logs); 403 shows “Not authorized”. |
| **GET /admin/users** | Implemented | Returns list of users including tokens_remaining, bot_status. |
| **GET /admin/users/export** | Implemented | CSV download (admin only). |
| **PATCH /admin/users/{user_id}** | Implemented | Update plan_tier, lending_limit, rebalance_interval, pro_expiry, tokens_remaining. |
| **GET /admin/api-failures** | Implemented | Returns in-memory API failure log (limit 100–200). |
| **POST /admin/api-failures/retry** | Implemented | Retry gross profit refresh by failure_id or user_id. |
| **POST /admin/bot/start/{user_id}** | Implemented | Admin-only start bot for any user. |
| **POST /admin/bot/stop/{user_id}** | Implemented | Admin-only stop bot for any user. |
| **GET /admin/bot/logs/{user_id}** | Implemented | Admin-only terminal logs for any user. |
| **POST /admin/arq/restart** | Implemented | Placeholder (worker must be restarted externally). |
| **GET /admin/deduction/logs** | Implemented | Recent deduction log entries. |
| **POST /admin/deduction/trigger** | Implemented | Manual run of daily token deduction. |
| **POST /admin/deduction/rollback/{user_id}/{date}** | Implemented | Add back tokens for user/date from in-memory log. |
| **GET /admin/health** | Implemented | Redis and DB status. |
| **GET /admin/logs/errors** | Implemented | Same as api-failures. |
| **GET /admin/audit-logs** | Implemented | Immutable audit log of admin actions. |

## 5. Implemented (post-delivery)

- Redirect and admin page auth (session + getBackendToken, 403 handling).
- User management: list with tokens_remaining and bot_status, search/filter, CSV export, plan tier and tokens_remaining edit.
- Bot control: admin start/stop per user, bot logs (terminal) per user, ARQ restart placeholder.
- Deduction: logs table, manual trigger, rollback by user_id and date.
- System health: Redis and DB status; error log (API failures) in UI.
- Admin audit logs: immutable in-memory log; GET /admin/audit-logs; UI section “Audit Logs”.

## 6. Optional / not implemented

- Subscription/payment management (admin subscriptions history, token adjust is done via user edit).
- API key management (view masked / reset) – not implemented.
- Notifications (bulk send, delivery logs) – not implemented.
- Admin settings (global deduction time, rate limits) – not implemented.

## 7. Fixes applied

| Fix | Description |
|-----|-------------|
| **Admin redirect** | After login, if `session.user.email === ADMIN_EMAIL` redirect to `/admin`; else keep `/dashboard`. |
| **Admin page session** | Use `useSession()` and `getBackendToken()`; call `/admin/users` with Bearer token; on 403 show “Not authorized”; remove paste-token flow. |
| **Email spelling** | Code uses `ngaiwachoi@gmail.com`; spec mentioned `ngaiwanchoi@gmail.com`. Use single constant (e.g. env `ADMIN_EMAIL`) so it can be updated in one place. |

## 8. File reference

- Backend admin: `main.py` (get_admin_user, `/admin/users`, `/admin/users/{id}`, `/admin/api-failures`, `/admin/api-failures/retry`).
- Frontend admin: `frontend/app/admin/page.tsx`.
- Auth: `frontend/app/api/auth/[...nextauth]/route.ts`, `frontend/app/api/auth/token/route.ts`, `frontend/lib/auth.ts`.
- Models: `models.py` (User has no `role`; admin by email only).
