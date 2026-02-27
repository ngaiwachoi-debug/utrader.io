# Fixed Start/Stop Bot Buttons – Validation Guide

## How to Apply the Fix

1. **Replace/update files** (already applied in repo):
   - **Backend:** `main.py` — `_enqueue_bot_task` (clear ARQ keys before enqueue), `/bot-stats` (active from DB `bot_status`), `/start-bot` and `/stop-bot` (idempotent, logging, response `bot_status`), same for `/start-bot/{user_id}` and `/stop-bot/{user_id}`.
   - **Frontend:** `frontend/components/dashboard/live-status.tsx` — `handleStart` / `handleStop` set `botActive` from response and call `refreshStatus()` on success.
   - **Worker:** `worker.py` — comments only; state sync (running/stopped) was already correct.

2. **Restart services:**
   - Restart the FastAPI backend (e.g. `uvicorn main:app` or PM2/systemd).
   - Restart the ARQ worker so it picks up the same Redis/DB state (e.g. `python -m arq worker.worker.WorkerSettings` or your run script).

3. **No DB migrations** — uses existing `users.bot_status` column.

---

## How to Test Auto-Start (Valid API Keys)

1. Register or use a test user (e.g. via UI or `POST /dev/create-test-user` with `ALLOW_DEV_CONNECT=1`).
2. Log in and get a JWT (e.g. `POST /dev/login-as` with the user email).
3. Save **valid** Bitfinex API keys:
   - **UI:** Settings → Connect Exchange (enter key/secret, submit).
   - **API:** `POST /connect-exchange` with `Authorization: Bearer <JWT>` and body `{"bfx_key":"...","bfx_secret":"..."}`.
4. **Expect:** After a successful save, the backend calls `_trigger_bot_start_after_keys_saved`, which enqueues the bot job and sets `bot_status = "starting"`. Worker picks up the job and sets `bot_status = "running"`.
5. **Verify:** Open Live Status (or call `GET /bot-stats/{user_id}` with JWT). Within a short time you should see `active: true` and status Running (either from DB `bot_status` or from Redis heartbeats).

---

## How to Test Manual Start/Stop (UI)

1. Ensure the user has valid API keys and is not expired.
2. **Start Bot:** On Live Status, click **Start Bot**.  
   - **Expect:** Button shows "Starting...", then badge shows Running (or Starting). No error toast.  
   - Backend logs: `start_bot user_id=... action=start enqueued=True bot_status_before=stopped bot_status_after=starting`.
3. **Stop Bot:** Click **Stop Bot**.  
   - **Expect:** Button shows "Stopping...", then badge shows Stopped. No error.  
   - Backend logs: `stop_bot user_id=... action=stop aborted=True/False bot_status_before=... bot_status_after=stopped`.
4. **Start again:** Click **Start Bot** again.  
   - **Expect:** Bot starts again (no "duplicate job" or stuck state).
5. **Duplicate Start (idempotent):** With bot already running (or queued), click **Start Bot** again.  
   - **Expect:** 200 success, message like "Bot already running or queued." No error; badge stays Running.

---

## How to Verify Terminal Logs (Start/Stop State)

1. **Backend:** Tail the FastAPI process logs. On each Start Bot you should see a line like:
   - `start_bot user_id=X action=start enqueued=True bot_status_before=stopped bot_status_after=starting`
   - or `enqueued=False (already running/queued)` when idempotent.
2. On each Stop Bot:
   - `stop_bot user_id=X action=stop aborted=True/False bot_status_before=... bot_status_after=stopped`
3. **ARQ worker:** You should see `[bot_user_X] Booting Lending Engine for User X...` when a start is picked up, and `[INFO] Cleanup complete for User X` when the task exits (stop or crash).

---

## How to Confirm No Regressions

| Area | Check |
|------|--------|
| **Daily token deduction** | 10:15 UTC job still runs (or use `TEST_SCHEDULER_SECONDS` and confirm deduction log). |
| **Token Balance API** | `GET /api/v1/users/me/token-balance` (or your token balance route) still returns correct balance. |
| **Auto-start after API key save** | Saving valid keys still enqueues the bot and sets `bot_status = "starting"`. |
| **Frontend 5s polling** | Live Status still polls `GET /bot-stats/{user_id}` every 5s; badge and buttons update (and now also update immediately on Start/Stop success). |

---

## Validation Scripts (Cross-Platform)

- **Bash:** `chmod +x scripts/test_bot_buttons.sh` then `./scripts/test_bot_buttons.sh`  
  Optional: `BFX_KEY=... BFX_SECRET=... ./scripts/test_bot_buttons.sh` to test with real keys (auto-start).
- **PowerShell:** `.\scripts\test_bot_buttons.ps1`  
  Optional: `$env:BFX_KEY="..."; $env:BFX_SECRET="..."; .\scripts\test_bot_buttons.ps1`

Scripts will:
1. Create a test user and get JWT.
2. Optionally connect valid API keys (if BFX_KEY/BFX_SECRET set).
3. POST /start-bot (JWT) → expect success and `bot_status` in response.
4. Poll /bot-stats until `active: true`.
5. POST /stop-bot (JWT) → expect success and `bot_status: stopped`.
6. POST /start-bot again → success.
7. POST /start-bot again (duplicate) → success (idempotent).
8. GET /terminal-logs → expect lines.

Requires backend with `ALLOW_DEV_CONNECT=1` and ARQ worker running.

---

## Validation run (automated)

- **Backend:** Confirmed reachable at `http://127.0.0.1:8000`.
- **DB:** `users.bot_status` column was missing; `python migrations/run_bot_status_migration.py` was run successfully (PostgreSQL).
- **Script:** `scripts/validate_bot_buttons_local.py` was used (no dev endpoints; uses DB + NEXTAUTH_SECRET to build JWT for `choiwangai@gmail.com`).
- **Result:** Step 1 (Backend health) passed. Step 2 (Start Bot) returned **500 Internal Server Error** — typically caused by Redis unavailable or an uncaught exception in the start-bot path. Ensure **Redis is running** and **REDIS_URL** is set in `.env`; ensure the **ARQ worker** is running so enqueued jobs are processed.

**To get a full pass:** Start Redis, set `REDIS_URL` in `.env`, restart the backend, start the ARQ worker (`python scripts/run_worker.py`), then run:

```bash
python scripts/validate_bot_buttons_local.py
```

**If using dev endpoints** (create-test-user, login-as): set `ALLOW_DEV_CONNECT=1` and `NEXTAUTH_SECRET` in the environment when starting the backend, then run `.\scripts\test_bot_buttons.ps1` (PowerShell) or `./scripts/test_bot_buttons.sh` (Bash) with optional `BFX_KEY`/`BFX_SECRET` for auto-start.

---

## Troubleshooting

| Issue | What to do |
|-------|------------|
| **Start Bot returns 500** | Check backend logs for traceback. Usually Redis (REDIS_URL) or DB. Start Redis and ensure REDIS_URL is set. |
| **Start Bot returns 503** | "Queue service unavailable" — Redis not reachable or timeout. Start redis-server or check REDIS_URL. |
| **Bot never becomes active (poll timeout)** | ARQ worker not running or not connected to same Redis. Run `python scripts/run_worker.py`. |
| **create-test-user / login-as 404** | Backend must be started with `ALLOW_DEV_CONNECT=1`. Use `validate_bot_buttons_local.py` if you cannot set that. |
| **column users.bot_status does not exist** | Run `python migrations/run_bot_status_migration.py` once. |
