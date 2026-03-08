# Fix Bot Logs and Further Errors – Plan

## What the logs show

### 1. Worker terminal (ARQ)

| Time     | Event |
|----------|--------|
| 13:15:15 | Worker started, 1 function: `run_bot_task` |
| 13:18:57 | Job `bot_user_2:run_bot_task(2)` picked up (0.04s) |
| 13:19:16 | Health: `j_ongoing=1` **`queued=1`** (one job running, one queued) |
| 13:19:17 | **20.20s ! bot_user_2:run_bot_task max retries 1 exceeded** |
| 13:19:46 | Health: `j_failed=1`, `j_retried=0`, `j_ongoing=0`, `queued=0` |

**Observations:**

- The bot job ran ~20s then ARQ reported **“max retries 1 exceeded”** (job marked as failed, no retry because `max_tries=1`).
- **No exception or traceback** is shown in the worker log (no `[CRITICAL] Worker failed`, no `[SHUTDOWN] Task … cancelled`). So we cannot see the real failure reason from the current logs.
- **`queued=1` while `j_ongoing=1`** means two jobs for the same queue were present (one running, one waiting). That can be from:
  - A second Start (e.g. double-click or two requests), or
  - Start → abort of previous job → enqueue new job, with the old job still in “running” until it exits.

So we have two separate issues:

1. **Unknown failure reason** – ARQ says the job failed but we don’t log (or don’t see) the actual exception/cancel.
2. **Possible double job / abort** – two jobs in the queue for the same user; if the first was aborted, ARQ may still report it as “failed” (“max retries exceeded”).

### 2. Backend terminal (uvicorn)

- **ERROR: [Errno 10048] … only one usage of each socket address … is normally permitted**  
- Port **8000** was already in use when starting uvicorn again (e.g. another backend or previous run still bound).  
- This is **environmental**: not a code bug, but something to handle when “restart servers”.

---

## Root causes (inferred)

1. **“max retries 1 exceeded”**
   - Either the task **raised an exception** that we don’t log with traceback (so we don’t see it), or
   - The task was **aborted** (e.g. `job.abort()` from `_abort_bot_job_if_running` on a second Start), and ARQ records aborted jobs as failed and prints “max retries 1 exceeded”.
   - We need **explicit logging** so we can tell: real exception vs. graceful cancel/abort.

2. **Two jobs (j_ongoing=1, queued=1)**
   - Start path does: abort existing job → clear keys → enqueue new job.
   - If the user (or UI) calls Start twice in a short window, we can enqueue a second job before the first has finished exiting. So we can have one running + one queued.
   - Abort only signals the running job to stop; it doesn’t remove the “running” job from the queue instantly. The second enqueue is then valid and we get two jobs.

3. **Port 8000 in use**
   - No code change; operational (kill process on 8000 or use another port).

---

## Plan

### Step 1: Log real failure reason in the worker (required)

**Goal:** Whenever `run_bot_task` fails (exception or cancel), the worker stdout and, where useful, the user’s terminal log should show the reason.

**Changes in `worker.py`:**

1. **Traceback on Exception**
   - In `except Exception as e:`, add:
     - `import traceback`
     - `traceback.print_exc()` (or `print(traceback.format_exc())`) so the full traceback appears in worker stdout.
   - Optionally append a short one-line summary to `terminal_logs` (e.g. “Failure: &lt;type&gt;: &lt;message&gt;”) if not already there, so the dashboard shows something.

2. **Explicit “aborted” / “cancelled” message**
   - In `except asyncio.CancelledError:`, add a single **print** (worker stdout) before the existing logic, e.g.  
     `print(f"[SHUTDOWN] User {user_id} job cancelled or aborted (CancelledError). Exiting normally.")`  
   - So when the job is aborted (or stopped), we see one clear line in the worker log and can distinguish “cancelled” from “exception”.

3. **Optional: one-line exit summary to terminal_logs**
   - At the end of `run_bot_task` (e.g. in a common path or in `finally`), push one line to `terminal_logs` when the task exits:
     - “Bot task ended: stopped by user” (when we handled CancelledError),
     - “Bot task ended: error – &lt;type&gt;: &lt;message&gt;” (when we handled Exception),
     - “Bot task ended: cleanup” (normal/other).
   - This helps the dashboard show why the run stopped without needing worker stdout.

**Verification:** Run the bot, then either trigger an error (e.g. invalid key) or abort (second Start or Stop). Worker terminal must show either a traceback (exception) or the “[SHUTDOWN] … cancelled or aborted” line (cancel/abort). Dashboard terminal tab should show a clear “Failure: …” or “Shutdown: …” when applicable.

---

### Step 2: Avoid “max retries exceeded” being confusing for aborts (optional)

**Goal:** When the job is aborted (CancelledError), we don’t want ARQ to report it as a “failure” if we can avoid it, so logs are less misleading.

**Options:**

- **A.** Leave as-is: ARQ may still report “max retries 1 exceeded” for aborted jobs. With Step 1, we’ll at least see “[SHUTDOWN] … cancelled or aborted” in the worker and know it wasn’t a real exception.
- **B.** In `worker.py`, wrap the **entire** `run_bot_task` body in a top-level `try/except BaseException` (or `except Exception` and then a separate `except BaseException` for CancelledError). In the CancelledError path, do the same cleanup as now but **return** normally (don’t re-raise). Some ARQ versions might still count “task was cancelled” as failure; this improves the chance the job is considered “completed” rather than “failed”.

Recommendation: implement **Step 1** first; only add **B** if you still see “max retries exceeded” for normal Stop/second Start and want to try to clear that message.

---

### Step 3: Reduce double-enqueue (optional)

**Goal:** Avoid having two jobs (one running, one queued) for the same user when the user clicks Start once (or twice quickly).

**Options:**

- **A.** **Cooldown on start:** You already have `_check_start_cooldown`; ensure the cooldown is long enough (e.g. 10–15 s) after a Start so a double-click doesn’t enqueue twice.
- **B.** **Debounce in UI:** Disable the Start button for a few seconds after click and/or ignore duplicate start requests (you may already have this).
- **C.** **Abort then short delay before enqueue:** In `main.py`, after `await _abort_bot_job_if_running(redis, user_id)`, `await asyncio.sleep(1)` (or 2) so the aborted job has time to exit and release the slot before we enqueue the new job. Reduces the chance of “running + queued” at the same time. Downside: every Start is delayed by 1–2 s.

Recommendation: only add **C** if you still see `queued=1` with `j_ongoing=1` after Step 1 and want to reduce it; otherwise rely on cooldown and UI.

---

### Step 4: Port 8000 already in use (operational)

**Goal:** Avoid “only one usage of each socket address” when restarting the backend.

**Actions (no code change):**

- Before starting uvicorn again, either:
  - Stop the process that is using port 8000 (e.g. previous uvicorn or another app), or
  - Use another port, e.g. `uvicorn main:app --host 127.0.0.1 --port 8001`, and point the frontend/Stripe to that port if needed.

---

## Order of implementation

| Step | Item | Files | Priority |
|------|------|--------|----------|
| 1 | Log traceback on Exception; print on CancelledError; optional one-line exit summary to terminal_logs | worker.py | **Required** |
| 2 | (Optional) Top-level catch of CancelledError so aborted jobs don’t look like failures | worker.py | Optional |
| 3 | (Optional) Short delay after abort before enqueue, or tighten start cooldown | main.py | Optional |
| 4 | (Operational) Free port 8000 or use another port before starting backend | — | When restarting |

---

## Verification checklist

After Step 1:

- [ ] Start bot for user 2; in worker terminal you see either “Booting Lending Engine…”, then either “Found 2 funding wallet(s)” / TICKET ISSUED, or a clear error/traceback.
- [ ] Trigger a real error (e.g. temporarily break API key); worker must print full traceback; dashboard terminal should show “Failure: …”.
- [ ] Stop bot (or Start again so first job is aborted); worker should print “[SHUTDOWN] … cancelled or aborted” (and optionally “Shutdown: task cancelled” in dashboard).
- [ ] If ARQ still prints “max retries 1 exceeded”, you can tell from the new logs whether it was an exception (traceback) or an abort (SHUTDOWN line).

Once this is in place, we can use the next run’s logs to fix any remaining application errors (e.g. Bitfinex 10114/10001, or missing keys) with full context.
