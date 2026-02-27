# Start/Stop Bot Buttons – Root Cause Report

## Summary

The "Start Bot" and "Stop Bot" buttons were non-functional due to **three root causes**: ARQ re-enqueue blocking, `/bot-stats` not reflecting DB state before worker heartbeats, and stop endpoint returning an error when the bot was already stopped (breaking idempotency and frontend handling).

---

## 1. ARQ Job Key Not Cleared Before Enqueue (Primary)

**Symptom:** Clicking "Start Bot" after a previous run (or after "Stop Bot") did not enqueue the job; `bot_status` stayed "stopped".

**Root cause:** The Python ARQ library blocks re-enqueueing a job with the same `_job_id` while **any result or job key** for that ID still exists in Redis. After a job completes or is aborted, ARQ can leave `arq:result:job_id` (and sometimes `arq:job:job_id`) in Redis. Our code only called `_clear_arq_job_keys()` **after** the first `enqueue_job()` returned `None`, then retried once. In practice, the first enqueue often returned `None` due to leftover keys, and the single retry after clear was not always sufficient under load or with certain Redis/ARQ versions. The reliable fix is to **clear ARQ keys before every enqueue**, not only on retry.

**Evidence (conceptual):**
- ARQ issue: "Cannot enqueue job with a _job_id again, despite execution of the job being fully completed" (result key persists).
- Our keys: `arq:job:bot_user_{id}`, `arq:result:bot_user_{id}`, and member in `arq:queue`. Clearing these before enqueue allows the same `job_id` to be used again.

**Fix applied:** In `_enqueue_bot_task()`, call `_clear_arq_job_keys(redis, job_id)` **before** the first `redis.enqueue_job(...)`. Kept the clear+retry path for robustness.

---

## 2. `/bot-stats` Active Only From Redis Heartbeats (UI Lag)

**Symptom:** After clicking "Start Bot", the UI sometimes showed "Stopped" for several seconds until the worker wrote heartbeat keys.

**Root cause:** `/bot-stats/{user_id}` set `active: True` only when Redis keys `status:{user_id}:*` (engine heartbeats) existed. Right after start, the API set `users.bot_status = 'starting'` and the job was queued, but the worker had not yet written any heartbeat, so the endpoint returned `active: False`. The frontend uses `data.active` for the badge and buttons, so the UI showed "Stopped" until the worker booted and pushed heartbeats.

**Fix applied:** `/bot-stats` now sets `active = True` when either (1) there is at least one engine heartbeat key, or (2) `users.bot_status` is `"running"` or `"starting"`. So the UI shows Running/Starting as soon as the API has updated the DB.

---

## 3. Stop Bot Returned Error When Already Stopped (Idempotency)

**Symptom:** "Stop Bot" when the bot was already stopped could show an error or confuse the UI.

**Root cause:** When `job.abort()` did not find a running job (already stopped), the code still set `bot_status = "stopped"` but returned `{"status": "error", "message": "No active bot found"}`. The frontend treated this as a failed request. Idempotent stop should always return success when the bot is stopped (no orphaned jobs).

**Fix applied:** Stop endpoints always set `bot_status = "stopped"`, clear ARQ keys, and return `{"status": "success", "message": "Bot stopped." or "Shutdown signal sent", "bot_status": "stopped"}`. No more `status: "error"` for "already stopped".

---

## 4. Frontend Not Updating Immediately on Success

**Symptom:** User had to wait for the 5s polling cycle to see the status change after Start/Stop.

**Root cause:** Start/Stop handlers called `refreshStatus()` after success but did not set `botActive` from the API response. Combined with cause #2, the next poll could still see `active: false` until the worker wrote heartbeats.

**Fix applied:** (1) Backend returns `bot_status` in start/stop responses. (2) Frontend on start success: if `data.bot_status` is `"running"` or `"starting"`, set `setBotActive(true)` immediately. (3) Frontend on stop success: set `setBotActive(false)` immediately. Then call `refreshStatus()` so the rest of the data stays in sync.

---

## 5. Auto-Start After API Key Save

**Root cause:** Auto-start uses the same `_enqueue_bot_task()`. Once we clear ARQ keys before enqueue, auto-start after valid API key save works without change; no skipped auto-start fix was required beyond the enqueue fix.

---

## Log Snippets (Text-Based)

- **Before fix (conceptual):** Backend logs might show no "start_bot" entries; worker never receives job after a prior run. Redis: `arq:result:bot_user_1` present after job end.
- **After fix:** Backend logs: `start_bot user_id=1 action=start enqueued=True bot_status_before=stopped bot_status_after=starting`. Worker: `[bot_user_1] Booting Lending Engine for User 1...`.

---

## Files Changed

| Area        | File(s) |
|------------|---------|
| Backend    | `main.py` (`_enqueue_bot_task`, `/bot-stats`, `/start-bot`, `/stop-bot`, `/start-bot/{user_id}`, `/stop-bot/{user_id}`) |
| Frontend   | `frontend/components/dashboard/live-status.tsx` (handleStart, handleStop) |
| Worker     | `worker.py` (comments only; state sync logic already correct) |
