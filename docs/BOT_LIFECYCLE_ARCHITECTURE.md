# Bot Lifecycle Architecture (uTrader.io)

## 1. Text-based architecture diagram

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           USER REGISTRATION / API KEY SETUP                       │
└─────────────────────────────────────────────────────────────────────────────────┘
    │
    │  User signs up (Google or dev)  →  User saves Bitfinex API keys
    │  POST /auth/google              →  POST /connect-exchange
    │  or POST /connect-exchange/by-email  or /connect-exchange/by-user
    │
    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  Backend: _validate_and_save_bitfinex_keys()                                     │
│  • Validates keys with Bitfinex API                                               │
│  • Saves to api_vault (encrypted)                                                 │
│  • On success → _trigger_bot_start_after_keys_saved(user_id, db)                 │
└─────────────────────────────────────────────────────────────────────────────────┘
    │
    │  Auto-start (no manual "Start Bot" required)
    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  _trigger_bot_start_after_keys_saved()                                           │
│  • get_redis() → _enqueue_bot_task(redis, user_id)                              │
│  • Sets users.bot_status = 'starting'                                             │
│  • Does not raise on Redis failure (keys save still succeeds)                    │
└─────────────────────────────────────────────────────────────────────────────────┘
    │
    │  ARQ queue
    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  Redis (ARQ)                                                                      │
│  • Queue: arq:queue (ZSET)                                                        │
│  • Job key: arq:job:bot_user_{user_id}                                           │
│  • Result: arq:result:bot_user_{user_id} (keep_result=0 so often absent)         │
└─────────────────────────────────────────────────────────────────────────────────┘
    │
    │  Worker picks job
    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  ARQ Worker (scripts/run_worker.py)                                               │
│  • run_bot_task(ctx, user_id)                                                     │
│  • Sets users.bot_status = 'running'                                              │
│  • Pushes terminal_logs:{user_id} to Redis                                         │
│  • Runs bot_engine.PortfolioManager (heartbeat → status:{user_id}:*)              │
│  • On exit/cancel: users.bot_status = 'stopped'                                   │
└─────────────────────────────────────────────────────────────────────────────────┘
    │
    ├──────────────────────────────────┬──────────────────────────────────────────┐
    ▼                                  ▼                                            ▼
┌─────────────────────┐  ┌─────────────────────────────┐  ┌────────────────────────┐
│  MANUAL STOP         │  │  MANUAL START               │  │  STATUS & LOGS         │
│  POST /stop-bot      │  │  POST /start-bot            │  │  GET /bot-stats/{id}   │
│  • Job.abort()       │  │  • _enqueue_bot_task()      │  │  • Redis status:*      │
│  • users.bot_status  │  │  • Clear ARQ keys if needed │  │  • users.bot_status    │
│    = 'stopped'       │  │  • users.bot_status         │  │  GET /terminal-logs/id │
│                      │  │    = 'starting'             │  │  • Redis terminal_logs │
└─────────────────────┘  └─────────────────────────────┘  └────────────────────────┘
    │                                  │                                            │
    └──────────────────────────────────┴────────────────────────────────────────────┘
                                                    │
                                                    ▼
┌─────────────────────────────────────────────────────────────────────────────────┐
│  Frontend                                                                         │
│  • Live Status: polls GET /bot-stats every 5s → shows Running/Stopped             │
│  • Start Bot / Stop Bot buttons → POST /start-bot, POST /stop-bot                  │
│  • Terminal: polls GET /terminal-logs/{userId} every 2s → shows log lines         │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Current architecture (summary)

| Question | Answer |
|----------|--------|
| **How is the bot hosted?** | Single ARQ worker process (Python). One task per user; job_id = `bot_user_{user_id}`. Not per-user Docker or serverless. |
| **How is bot state persisted?** | (1) **Redis**: heartbeat keys `status:{user_id}:*` → "active" when present. (2) **DB**: `users.bot_status` (`stopped` \| `starting` \| `running`) for persistence and UI. |
| **What triggers the bot to start?** | (1) **Auto**: After API key save (`/connect-exchange`, `/connect-exchange/by-email`, `/connect-exchange/by-user`) → `_trigger_bot_start_after_keys_saved()`. (2) **Manual**: POST `/start-bot` or `/start-bot/{user_id}`. |

---

## 3. Known issues (addressed)

| Issue | Cause | Fix |
|-------|--------|-----|
| **Start Bot button non-functional** | ARQ refuses re-enqueue when `arq:job:` or `arq:result:` for same job_id still exists (e.g. after Stop). | Before enqueue, clear `arq:job:{id}`, `arq:result:{id}`, and ZREM from `arq:queue`. Then enqueue (idempotent). |
| **Fixes breaking other functions** | Shared job_id and stale Redis keys; no single place for "clear then enqueue". | Centralized `_enqueue_bot_task()` and `_clear_arq_job_keys()`. |
| **Terminal sometimes no logs** | Bot not running, or worker not pushing to Redis quickly. | Worker pushes a boot line immediately; auto-start on key save so bot runs without manual Start. |

---

## 4. Code changes (summary)

### Backend (main.py)

- **Auto-start**: `_trigger_bot_start_after_keys_saved(user_id, db)` called after successful key save in `/connect-exchange`, `/connect-exchange/by-email`, `/connect-exchange/update-by-email`, `/connect-exchange/by-user`.
- **Start/Stop idempotent**: `_clear_arq_job_keys(redis, job_id)` deletes `arq:job:`, `arq:result:`, and ZREM from `arq:queue`. `_enqueue_bot_task(redis, user_id)` tries enqueue, on failure clears keys and retries once.
- **bot_status**: Set `users.bot_status = 'starting'` on start (API); worker sets `'running'` when task runs and `'stopped'` in `finally`. Stop endpoints set `'stopped'`.
- **/bot-stats**: Returns `bot_status` from DB in response.

### Backend (worker.py)

- On task start (after loading user/keys): `user.bot_status = 'running'`, commit.
- In `finally`: set `users.bot_status = 'stopped'`, commit.

### Database

- **users.bot_status** (String, default `'stopped'`). Add column by running the migration:

  - **File**: `migrations/add_bot_status_to_users.sql`
  - **PostgreSQL**: `psql $DATABASE_URL -f migrations/add_bot_status_to_users.sql`
  - **SQLite**: `sqlite3 your.db "ALTER TABLE users ADD COLUMN bot_status VARCHAR(20) DEFAULT 'stopped';"` (run once; if you get "duplicate column name", the column already exists.)
  - **Both (recommended)**: `python migrations/run_bot_status_migration.py` (idempotent; ignores "column already exists").

#### Migration debug guide

| Symptom | Cause | Fix |
|--------|--------|-----|
| **PostgreSQL: "column already exists"** | Column was added earlier. | No action; migration is already applied. |
| **PostgreSQL: "permission denied"** | DB user lacks ALTER on `users`. | Grant `ALTER ON TABLE users` to the app user, or run the migration as a superuser. |
| **SQLite: "duplicate column name"** | Column already added. | Safe to ignore; or use `python migrations/run_bot_status_migration.py` next time (it catches this). |
| **SQLite: "no such table: users"** | DB file is new or wrong path. | Ensure `DATABASE_URL` points to the correct SQLite file and that the `users` table exists (run app once to create schema, or apply prior migrations). |
| **Script: "No module named psycopg2"** | PostgreSQL driver missing. | `pip install psycopg2-binary` for PostgreSQL. |

### Frontend (live-status.tsx)

- Poll GET `/bot-stats/{userId}` every 5s and set `botActive` from `data.active` so the Running/Stopped badge updates without full refresh.

---

## 5. Step-by-step test plan

1. **Register + API keys → auto-start**
   - Register a new user (or use dev) and save Bitfinex API keys (Settings or connect-exchange).
   - **Expect**: No error; backend enqueues bot; within ~15s, Terminal shows "Bot started for user X. Loading..." and Live Status shows Running (or Starting then Running).
   - **Check**: GET `/bot-stats/{user_id}` returns `active: true` and `bot_status: "running"` once worker has started.

2. **Terminal logs**
   - With bot running, open Terminal tab.
   - **Expect**: Log lines appear (refresh every 2s); new lines appear as the bot runs.

3. **Stop Bot**
   - On Live Status, click "Stop Bot".
   - **Expect**: Button shows "Stopping..."; then "Start Bot" appears; status badge shows Stopped; Terminal stops getting new lines.
   - **Check**: GET `/bot-stats/{user_id}` returns `active: false`, `bot_status: "stopped"`.

4. **Start Bot again**
   - Click "Start Bot".
   - **Expect**: Bot queued; within ~15s status shows Running and Terminal logs resume.
   - **Check**: No "Bot already running or queued" unless bot was already running; re-enqueue after stop works.

5. **No regressions**
   - Run existing tests (registration tokens, subscription, deposit form).
   - Save API keys again (update) and confirm bot auto-starts again (or stays running).
   - Confirm Settings and other pages still load and work.

6. **Invalid Bitfinex API keys → bot does NOT auto-start**
   - Call connect-exchange (or by-email/by-user) with invalid key/secret (e.g. wrong length or fake keys).
   - **Expect**: API returns 400 with error (e.g. "Invalid Keys. Unable to verify Bitfinex account."); keys are not saved; bot is not started. Backend must not call `_trigger_bot_start_after_keys_saved` when validation fails.
   - **Check**: GET `/bot-stats/{user_id}` shows `active: false`; no "Bot started" line in Terminal for that user.

7. **Multiple manual Start/Stop clicks → no race conditions**
   - With bot running, click "Stop Bot" then immediately click "Start Bot" (or double-click Start).
   - **Expect**: No duplicate bots; status settles to Running within ~15s; no 500 errors. Repeat Stop → Start several times.
   - **Check**: Only one bot task per user (worker logs one run per start); UI shows consistent state (idempotent behavior).

---

## 6. Terminal logs (polling and SSE compatibility)

- **Current**: Frontend polls `GET /terminal-logs/{user_id}` every **2s**. Backend returns `{ "lines": ["..."] }` from Redis list `terminal_logs:{user_id}`. Worker appends lines when the bot runs.
- **SSE later**: To add Server-Sent Events, keep the same URL and response shape for `GET /terminal-logs/{user_id}` (no `Accept: text/event-stream`). Add a new endpoint or the same path with `Accept: text/event-stream` returning a stream; frontend can then choose polling vs SSE. No breaking change to existing polling clients.

---

## 7. Reliability notes

- **Idempotent start**: Stop endpoint clears ARQ keys after abort so the next Start always enqueues cleanly. Start also clears-and-retries if enqueue returns None.
- **Auto-start only on valid keys**: `_trigger_bot_start_after_keys_saved` is called only after successful key validation and save (connect-exchange returns 200). Invalid keys → 400 → no auto-start.
- **bot_status in DB**: Gives a persistent view of intent/state even if Redis is flushed; worker and API keep it in sync.
