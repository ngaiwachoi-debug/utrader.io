# Plan: 1000 Users, One Job Per User, Production Standard

## Goals

1. **One user = at most one running bot job** – Enforced at enqueue time (abort + single job_id) and at run time (Redis lock so a second runner for the same user exits immediately).
2. **Scale to 1000 concurrent users** – DB pool, Redis usage, and worker behavior must be safe under load.
3. **Production standard** – Clear logging, no double-enqueue races, cooldowns and rate limits in place.

---

## Current State

| Area | Current | Notes |
|------|--------|--------|
| Job identity | `job_id = bot_user_{user_id}` | Only one job per user in ARQ queue. |
| Start path | Abort existing → clear keys → enqueue | Can still have a brief overlap (old job exiting, new job queued). |
| Worker | No per-user run lock | With multiple workers, two jobs for same user cannot run (single job_id); with abort race, old job may still be running when new one is queued. |
| Cooldown | 30s start, 15s stop; 10 actions/min | In-memory; fine for single API instance. |
| DB pool | Default (5 + 10 overflow) | Too small for many workers + API. |
| Logging | No traceback on exception; cancel not always visible | Hard to debug "max retries exceeded". |

---

## Changes (Implement and Run)

### 1. Worker: Redis run lock (one job per user at run time)

**Goal:** Guarantee only one active run per user. If a job starts and finds another run already holding the lock (e.g. abort delay not yet done), it exits without running.

**In `worker.py`:**

- Constants: `BOT_RUN_LOCK_KEY = "bot_run_lock:{user_id}"`, `BOT_RUN_LOCK_TTL_SEC = 7200` (2h max; crashed jobs don’t hold forever).
- **Acquire:** After token check and before creating `PortfolioManager`, do:
  - `lock_key = f"bot_run_lock:{user_id}"`
  - `lock_val = ctx.get("job_id", f"job_{user_id}")` (unique per job)
  - Redis: `SET lock_key lock_val EX BOT_RUN_LOCK_TTL_SEC NX`
  - If SET failed (key already set): log "Another run for this user is active; exiting.", push to terminal_logs, set `bot_status = "stopped"`, return. Do not start the engine.
- **Release:** In a `finally` block that runs for every exit path (success, cancel, exception), if we acquired the lock (e.g. we stored `lock_acquired = True` after SET), run: Redis `GET lock_key`; if value == `lock_val`, `DEL lock_key`. (Optional: use a small Lua script for atomic check-and-delete if Redis supports it; otherwise GET+DEL is acceptable.)

Effect: Only one worker process can hold the lock per user; a second job for the same user (e.g. queued after abort) will see the lock and exit without running.

---

### 2. Worker: Logging for 1000-user support

**Goal:** When a job fails or is cancelled, we see the reason (exception traceback or cancel) in worker stdout and optionally in the user’s terminal log.

**In `worker.py`:**

- **On Exception:** In `except Exception as e:`, add `import traceback` and `traceback.print_exc()` so worker stdout gets the full traceback.
- **On CancelledError:** Add one print at the start of the handler, e.g. `print(f"[SHUTDOWN] User {user_id} job cancelled or aborted (CancelledError). Exiting normally.")` so we can tell cancel vs exception.
- **Optional:** Push one line to `terminal_logs` when the task exits: "Bot ended: stopped by user" (cancel) or "Bot ended: error – &lt;type&gt;: &lt;msg&gt;" (exception).

---

### 3. Main: Short delay after abort before enqueue

**Goal:** Give the aborted job time to exit and release the Redis lock before we enqueue the new job, so we don’t have two jobs in flight for the same user.

**In `main.py`:**

- In all three start paths (e.g. after `await _abort_bot_job_if_running(redis, user_id)` and before `await _enqueue_bot_task(...)`), add:
  - `await asyncio.sleep(2)`
- So the sequence is: abort → wait 2s → clear keys → enqueue. This keeps "one user, one job" and avoids the new job seeing the old run’s lock.

---

### 4. Database: Connection pool for scale

**Goal:** Support many concurrent workers + API without running out of connections.

**In `database.py`:**

- In `create_engine(DATABASE_URL, ...)`, add:
  - `pool_size=50`
  - `max_overflow=100`
- So up to 150 connections total. Tune later if you run more workers or higher API concurrency.

---

### 5. Cooldown / rate limit (already in place)

- **Start cooldown:** 30s between starts per user (reduces double-start).
- **Rate limit:** 10 start/stop actions per minute per user.
- For 1000 users these are per-user and in-memory; fine for single API instance. For multi-instance API, consider moving to Redis later.

---

## Order of implementation

| Step | Item | File(s) |
|------|------|--------|
| 1 | Redis run lock: acquire before run, release in finally | worker.py |
| 2 | Logging: traceback on Exception, print on CancelledError | worker.py |
| 3 | Delay 2s after abort before enqueue | main.py |
| 4 | DB pool_size=50, max_overflow=100 | database.py |

---

## Implementation status

- **Done:** Redis run lock (worker), traceback + CancelledError logging (worker), 2s delay after abort (main), DB pool 50+100 (database.py).

## Verification

- **One job per user:** Start bot for user 2; while it’s running, start again (e.g. from another tab). Expect: first run holds lock; second job is enqueued after 2s delay, then when it runs it should either see the lock and exit with "Another run for this user is active" or, after the first is aborted, acquire the lock and run. No two concurrent runs for the same user.
- **Scale:** Run multiple workers; start bots for many users. Worker stdout should show no duplicate "Booting Lending Engine" for the same user at the same time; DB and Redis should stay within limits.
- **Logging:** Trigger an error (e.g. invalid key) and confirm worker prints full traceback; stop bot and confirm "[SHUTDOWN] … cancelled or aborted" in worker stdout.

---

## Summary

- **One user, one job:** Enforced by (1) single `job_id` per user, (2) abort-before-enqueue, (3) 2s delay after abort, (4) Redis run lock in the worker so a second run for the same user exits without starting.
- **1000 users:** DB pool increased; Redis used for lock and terminal_logs (already bounded per user); cooldowns and rate limits per user.
- **Standard:** Clear logging (traceback + cancel message), no silent failures.
