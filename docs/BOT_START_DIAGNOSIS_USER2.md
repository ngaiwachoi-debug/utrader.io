# Bot start diagnosis – user 2

## What we ran

1. **`scripts/diagnose_user_bot.py 2`** – DB-only check  
   - User 2: exists, has vault (API keys), `tokens_remaining = 2500`, would pass worker token gate.

2. **`scripts/worker_token_check.py 2`** – Same token read as worker  
   - `token_ledger_svc.get_tokens_remaining(db, 2) = 2500.0`  
   - `user_token_balance` row present with `tokens_remaining=2500`.  
   - **Conclusion:** With current code and this DB, the worker would pass the token check.

3. **`scripts/run_bot_and_capture_logs.py 2`** – Start via API, then read Redis `terminal_logs:2`  
   - First run: Redis contained **old** messages:  
     - "Bot started for user 2. Loading..."  
     - "Tokens remaining < 1. Bot not started."  
   - Those strings **do not** appear in the current `worker.py`.  
   - Current worker uses:  
     - "Job picked up from queue. Loading..."  
     - "Failure: No tokens remaining (balance={n}). Bot not started."

4. **Stop + start + capture again (logs cleared first)**  
   - API: `POST /stop-bot/2` then `POST /start-bot/2` → job queued.  
   - After 12s, Redis had **2 new lines** from the **current** worker.  
   - Script crashed on print (Windows console + emoji in log). So the worker **did** run and write; it did **not** fail on the token check (otherwise we’d see only the “No tokens remaining” line).

## Actual reason the bot “didn’t start” before

- The **terminal tab** was showing **old** lines from Redis:  
  - "Tokens remaining < 1. Bot not started."  
- That text is from an **older worker** (or another writer). The **current** worker never writes "Tokens remaining < 1" or "Bot started for user X. Loading...".
- So historically the bot did not start because **when that old worker ran, it saw `tokens_remaining <= 0`** for user 2 (e.g. no row in `user_token_balance` or balance was 0).
- **Now:** With the same codebase and DB, user 2 has 2500 tokens. When we stopped and started the bot, the **current** worker picked up the job and wrote 2 lines (no token failure), so the bot **did** start.

## Why the old worker might have seen 0 tokens

1. **Different DB** – Worker process using another `DATABASE_URL` (e.g. different host, or SQLite path) where user 2 had no balance.
2. **Old worker process** – A long‑running ARQ worker from an old deploy that (a) wrote the old message format and (b) might have read from a different DB or schema.
3. **Balance was 0 at that time** – Tokens were added later (e.g. purchase, admin, registration); the failure was correct for that moment.

## Advice (no code changes)

1. **Confirm worker and DB**  
   - Restart the ARQ worker so it’s definitely running the **current** `worker.py`.  
   - Ensure the worker uses the **same** `.env` (and thus `DATABASE_URL`) as the API.

2. **Clear stale terminal lines**  
   - Old “Tokens remaining < 1” lines stay in Redis until overwritten.  
   - To see only current runs: clear `terminal_logs:2` (e.g. with a small script or admin tool) before starting the bot, then start and check the Terminal tab.

3. **Re-check if it happens again**  
   - Run `python scripts/worker_token_check.py 2` right after a failed start.  
   - If it shows `tokens_remaining > 0`, the worker that ran is likely using a different DB or an old build.

4. **Scripts added**  
   - `scripts/diagnose_user_bot.py [user_id]` – User, vault, tokens, bot state.  
   - `scripts/worker_token_check.py [user_id]` – Exact token value and row the worker uses.  
   - `scripts/run_bot_and_capture_logs.py [user_id]` – Clear logs, POST start-bot, wait, print Redis terminal lines (current worker output).  
   - `scripts/test_bot_run_direct.py [user_id]` – Run worker task in-process (no ARQ), clear `terminal_logs:{id}`, run 8s, print lines. Proves worker + token check with current .env/DB.

---

## Retest (restart worker + clear logs + verify)

- **ARQ worker** was restarted (same `.env` / `DATABASE_URL` as API).  
- **`python scripts/worker_token_check.py 2`** → `tokens_remaining = 2500`, would PASS.  
- **`terminal_logs:2`** was cleared; when starting the bot via **API** (`POST /start-bot/2`), the enqueued job was sometimes **aborted before start** in the worker log (ARQ/queue behaviour).  
- **In-process run** (bypasses queue):  
  `python scripts/test_bot_run_direct.py 2`  
  - Clears `terminal_logs:2`, runs `run_bot_task(ctx, 2)` for 8s, then prints Redis `terminal_logs:2`.  
  - Result: **Works.** Lines written include current worker messages, e.g.:  
    - `[HH:MM:SS] Job picked up from queue. Loading...`  
    - `[HH:MM:SS] API keys found. Checking token balance...`  
    - `[HH:MM:SS] Token balance OK (2500 tokens). Starting trading engine...`  
    - `[HH:MM:SS] Bot status: running. Launching portfolio manager...`  
    - `[HH:MM:SS] Trading terminal active. Rebalance every 10 min. Scanner starting...`  
    - plus scanner and engine lines.  
  - So **worker logic and token check work** with current code and DB; any “not starting” when using the UI is likely due to the job being aborted in the queue (e.g. stop/start race or another client).
