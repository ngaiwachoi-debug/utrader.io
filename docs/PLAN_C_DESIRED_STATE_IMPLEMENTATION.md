# Plan C: Desired-State Bot Workflow — Implementation Plan

Replace the current start/stop bot flow with a **desired-state** model: API writes intent (`bot_desired_state`), worker reconciles (starts or stops the bot to match). Same user-facing behavior; no more "stuck at starting" when job is aborted before start.

---

## 1. Current vs Plan C (high level)

| Aspect | Current | Plan C |
|--------|---------|--------|
| **Intent** | Implicit: enqueue = "want running" | Explicit: `bot_desired_state` = "running" \| "stopped" |
| **Start** | Enqueue job → set `bot_status = "starting"` | Set `bot_desired_state = "running"` → enqueue **one** job per user |
| **Stop** | Abort job → clear keys → set `bot_status = "stopped"` | Set `bot_desired_state = "stopped"` → **then** set `bot_status = "stopped"` → abort + clear keys |
| **Worker** | Run bot if tokens/vault OK | **First** check desired state; if "stopped" → set `bot_status = "stopped"` and exit. If "running" → same as now (tokens, vault, run bot). |
| **Stuck "starting"** | Possible if job aborted before start and API DB update fails | Avoided: Stop **always** writes `bot_status = "stopped"` first; worker also reconciles on next run. |

---

## 2. Implementation phases

### Phase 1: Schema and model

- **1.1** Add column to `users` table:
  - `bot_desired_state` VARCHAR (e.g. 20), default `'stopped'`, nullable or not.
  - Allowed values: `'running'` | `'stopped'`.
- **1.2** Migration: new file e.g. `migrations/add_bot_desired_state.sql` with `ALTER TABLE users ADD COLUMN bot_desired_state VARCHAR(20) DEFAULT 'stopped';` (and backfill existing rows to `'stopped'` if needed).
- **1.3** In `models.py`, add to `User`:
  - `bot_desired_state = Column(String(20), default="stopped")  # running | stopped`.

**Deliverable:** DB has `bot_desired_state`; ORM exposes it.

---

### Phase 2: API — Start/Stop (user and admin)

- **2.1** `POST /start-bot` (authenticated user):
  - (Unchanged) Token check: if `tokens_remaining <= 0` → 400 INSUFFICIENT_TOKENS.
  - **New:** Set `current_user.bot_desired_state = "running"`, commit.
  - **Change:** Idempotency: if `bot_status in ("running", "starting")` **and** `bot_desired_state == "running"` → return "Bot already running or queued", no enqueue.
  - **Change:** Call `_enqueue_bot_task(redis, current_user.id)` (same helper; still enqueues `run_bot_task` with `job_id = bot_user_{id}`). If enqueue succeeds → set `bot_status = "starting"`, commit, return success. If enqueue fails (e.g. already queued) → still return success with "already running or queued" and refresh `bot_status`.
  - **Order:** Write `bot_desired_state` and `bot_status` in one transaction after enqueue.
- **2.2** `POST /stop-bot` (authenticated user):
  - **New (first):** Set `current_user.bot_desired_state = "stopped"` and `current_user.bot_status = "stopped"`, commit. (So UI never stuck on "starting".)
  - **Then:** Get Redis, `job_id = bot_user_{current_user.id}`, `Job(...).abort(timeout=5)`, `_clear_arq_job_keys(redis, job_id)`.
  - Return success, `bot_status: "stopped"`.
- **2.3** `POST /start-bot/{user_id}` (admin/dev, no auth for user):
  - Same logic as 2.1 but for `user_id`: token check optional or skip (admin can start without token check — confirm in Q&A). Set `user.bot_desired_state = "running"`, then enqueue, then `bot_status = "starting"` if enqueued.
- **2.4** `POST /stop-bot/{user_id}` (admin):
  - Same as 2.2 for given `user_id`: **first** set `user.bot_desired_state = "stopped"` and `user.bot_status = "stopped"`, commit; **then** abort job and clear keys.
- **2.5** Admin panel start/stop:
  - `POST /admin/bot/start/{user_id}`: same as 2.3 (set desired state, enqueue, set "starting").
  - `POST /admin/bot/stop/{user_id}`: same as 2.4 (set desired + status "stopped" first, then abort).

**Deliverable:** All start/stop endpoints use desired state and Stop always writes DB first.

---

### Phase 3: Autostart after first API key save

- **3.1** `_trigger_bot_start_after_keys_saved(user_id, db)`:
  - **Change:** Instead of enqueueing directly, set `user.bot_desired_state = "running"` and (if tokens >= 1) enqueue `run_bot_task(user_id)` and set `bot_status = "starting"` on success.
  - (Same as current behavior from user perspective; just consistent with desired-state model.)

**Deliverable:** First-time connect still auto-starts bot when tokens >= 1; desired state is set.

---

### Phase 4: Worker — reconcile on run

- **4.1** At the **very start** of `run_bot_task(ctx, user_id)` (after DB session and load user):
  - Reload or read `user.bot_desired_state` (from DB).
  - If `bot_desired_state == "stopped"` (or not "running"): set `user.bot_status = "stopped"`, commit, push terminal message e.g. "Desired state is stopped. Bot not started.", return (do not start the bot).
- **4.2** Rest of worker unchanged: if desired state is "running", proceed with vault check, token check, set `bot_status = "running"`, launch `PortfolioManager`, kill-switch loop, etc.
- **4.3** In the **kill-switch loop**, optionally re-check `bot_desired_state` each iteration (e.g. reload user from DB): if it becomes "stopped", cancel engine and exit, set `bot_status = "stopped"`. (So admin/user can click Stop and worker stops without relying only on job abort.)
- **4.4** On **any** exit (normal, exception, cancel): ensure `bot_status = "stopped"` in `finally` (already today). Optionally set `bot_desired_state = "stopped"` on exit only if you want worker to "clear" intent when it exits — **clarify in Q&A**.

**Deliverable:** Worker never starts bot when desired state is "stopped"; can optionally stop when desired flips to "stopped" mid-run.

---

### Phase 5: Optional — queue depth and rate limiting (Plan C scope)

- **5.1** Queue depth (backpressure): before enqueue in `_enqueue_bot_task`, check Redis queue length (e.g. ARQ queue size). If above threshold (e.g. 2× worker count), return False; API returns 503 "Too many bots starting. Try again later."
- **5.2** Per-user rate limit: e.g. max 1 start + 1 stop per 3–5 seconds per user (Redis key `ratelimit:bot:{user_id}` with TTL). If exceeded, return 429 or 503 with retry-after.

**Deliverable:** Optional; can be Phase 5 or later. Confirm in Q&A if you want this in first release.

---

### Phase 6: Other call sites and responses

- **6.1** Any endpoint that returns `bot_status` (e.g. `/bot-stats`, `/api/me` or user profile, admin exports): keep returning `bot_status` (actual state). Optionally also return `bot_desired_state` for admin/debug if useful.
- **6.2** Any place that sets `bot_status = "stopped"` (e.g. on key deletion, or admin actions): consider whether to also set `bot_desired_state = "stopped"` so worker and API stay in sync.
- **6.3** CSV export / admin list: add `bot_desired_state` column if desired; otherwise leave as-is.

**Deliverable:** No regression in UI or admin; optional exposure of desired state.

---

## 3. File change summary

| File | Changes |
|------|--------|
| `models.py` | Add `User.bot_desired_state`. |
| `migrations/add_bot_desired_state.sql` | New migration. |
| `main.py` | Start/stop endpoints (user + admin + legacy by user_id), autostart helper, optional queue/rate limit. |
| `worker.py` | Reconcile desired state at start; optional check in kill-switch loop. |

---

## 4. Testing checklist (after implementation)

- Start bot → `bot_desired_state = "running"`, `bot_status` goes "starting" then "running"; terminal shows bot.
- Stop bot → `bot_status` and `bot_desired_state` become "stopped" immediately in DB; job aborted; no stuck "starting".
- Stop before worker starts (abort before start) → DB already "stopped"; UI shows Stopped.
- Admin start/stop same behavior for any user_id.
- First-time connect (no vault before) → autostart sets desired state and enqueues when tokens >= 1.
- Worker: if desired state set to "stopped" before job runs, worker exits without starting bot and sets `bot_status = "stopped"`.

---

## 5. Questions (please confirm so behavior matches your expectations)

**Q1. Job name**  
Keep the worker task name as `run_bot_task` (only add desired-state check at the start), or rename to something like `reconcile_bot_user` and keep the same logic?

**Q2. Admin start without token check**  
For `POST /start-bot/{user_id}` and `POST /admin/bot/start/{user_id}`: should we **skip** the token check (so admin can start any user’s bot even with 0 tokens), or **keep** the same token check as user start and return 400 if tokens <= 0?

**Q3. Worker: set desired state on exit?**  
When the worker exits (normal stop, token exhaustion, or crash): should it set `bot_desired_state = "stopped"` in addition to `bot_status = "stopped"`, so “intent” always matches “actual” when the bot is not running? Or should only the **user/API** set desired state (worker only updates `bot_status`)?

**Q4. Kill-switch loop: check desired state?**  
In the worker’s main loop (every `rebalance_interval` minutes), should we **reload** `bot_desired_state` from DB and, if it’s "stopped", cancel the engine and exit? That way a Stop click stops the bot even if the job isn’t aborted quickly. Or is it enough to rely on job.abort() and only check desired state at job **start**?

**Q5. Queue depth and rate limiting in first release?**  
Should Phase 5 (queue depth limit + per-user rate limit) be part of the **first** Plan C release, or deferred to a later iteration?

**Q6. Autostart token threshold**  
Autostart after first API key save: keep “only if tokens >= 1”, or align with start-bot and use “tokens > 0” (same as POST /start-bot)?

**Q7. Idempotent start**  
When user clicks Start and we already have `bot_desired_state = "running"` and `bot_status in ("running", "starting)"`, we return “Bot already running or queued” without enqueueing again. Is that the desired behavior, or do you want to **always** enqueue one job on Start (and let the worker no-op if already running)?

**Q8. Legacy endpoints**  
`POST /start-bot/{user_id}` and `POST /stop-bot/{user_id}` (no auth, used by scripts/admin): should they behave **identically** to the authenticated start/stop (including desired state and “DB first” on stop), or do you need different behavior (e.g. no desired state, or different idempotency)?
