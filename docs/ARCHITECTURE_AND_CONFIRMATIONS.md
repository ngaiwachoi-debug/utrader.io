# Architecture and Confirmations

## 1. Task queue (1000+ users)

**Framework: ARQ** (Async Redis Queue), not Celery/Dramatiq.

- **Worker**: `worker.py` — ARQ worker with `run_bot_task(user_id)`. One job per user; job runs until stopped or token depletion.
- **Dispatcher**: FastAPI `POST /start-bot` and `POST /start-bot/{user_id}` enqueue `run_bot_task` with `_job_id=bot_user_{id}` so one running bot per user.
- **Redis**: Queue name `arq:queue`. Set `REDIS_URL` in env.
- **Stop bot**: `POST /stop-bot` uses `arq.jobs.Job(job_id, redis).abort()`. Worker must have `allow_abort_jobs = True` (set in `WorkerSettings`).

For a **stateless, one-cycle-per-job** design (recommended at scale), use `lending_worker_engine.run_one_lending_cycle()` inside the task and have a separate scheduler re-enqueue the user after `rebalance_interval` minutes.

---

## 2. Rate limiting (Bitfinex 10 req/s per IP)

- **Current**: No global rate limiter in code. Each user’s bot uses its own API keys; Bitfinex limits per API key and per IP.
- **At 1000 users**: All workers may share one IP. **Recommendation**: (1) Throttle inside the worker: e.g. global semaphore or Redis-based “max N concurrent Bitfinex requests per second” and delay tasks. (2) Or run 2–3 worker nodes on different IPs and shard users across them so no single IP hits 10 req/s.
- **429 handling**: `bot_engine` and Bitfinex service can retry with backoff on 429; consider a shared “cooldown” in Redis per IP when 429 is seen.

---

## 3. IP rotation

- **Not implemented** in this codebase.
- **Recommendation**: When a 429 (rate limit) is detected, mark that IP in Redis and switch to another proxy/VM. Use a proxy rotation service or multiple small VMs as “execution nodes” and round-robin or assign users to nodes. Implement a small test that calls Bitfinex until 429, then switch IP and retry.
- **Bitfinex**: Match request timing to their documented limits (e.g. 10 req/s per IP); space out requests in the worker (e.g. 0.15s between offer submits already in `bot_engine`).

---

## 4. API key storage (KMS)

- **Not a cloud KMS.** Keys are encrypted at rest using **AES-256-GCM** (or Fernet when `ENCRYPTION_KEY` is a valid Fernet key) in `security.py`.
- **Master key**: `ENCRYPTION_KEY` in the server environment. No plaintext API keys in the DB; `api_vault` stores `encrypted_key`, `encrypted_secret`, `encrypted_gemini_key`.
- **Decryption**: Only in process when the worker or API needs keys (e.g. `vault.get_keys()`). For a full KMS (e.g. AWS KMS, GCP KMS), you would use their APIs to decrypt in the worker instead of `ENCRYPTION_KEY`.

---

## 5. Gemini cost / strategy grouping

- **Not implemented.** Each user’s engine calls Gemini (e.g. `get_ai_insight`) per asset when deploying.
- **Recommendation**: “Strategy grouping”: bucket users by similar balance bands (e.g. $500–$5k, $5k–$50k). One shared AI run per bucket per interval; cache the strategy (e.g. in Redis) and reuse for all users in that bucket. Cuts Gemini calls by ~90% if many users share buckets.

---

## 6. Plan-specific rebalancing intervals

- **Enforced in** `worker.py` via `PLAN_CONFIG` and in `main.py` Stripe webhook:
  - **Pro**: 30 minutes
  - **AI Ultra**: 3 minutes  
  - **Whales**: 1 minute
- Worker loads `user.rebalance_interval` from config and sleeps that many minutes between kill-switch checks; the bot engine loop runs continuously until stopped, so effective “rebalance” is the sleep interval in the worker loop.

---

## 7. Token balance checking (login + 1h sync)

- **On login**: Frontend calls `/user-status/{user_id}`; backend computes `tokens_remaining` from `user_profit_snapshot` (no Bitfinex call). So token balance is checked on every dashboard load / login.
- **1-hour background sync**: No global cron in repo. Options: (1) Frontend polls `/user-status` every hour when the app is open. (2) Backend cron calls `/stats/{user_id}/lending` for active users every hour to refresh snapshot and thus token balance (costs Bitfinex API). (3) When the worker runs, it re-reads snapshot each cycle; if you add a periodic “refresh snapshot” job per user (e.g. every 1h), that keeps balances updated without extra login-time API.

---

## 8. Token rules (summary)

- **Usage**: 0.1 USD gross profit = 1 token used (10 tokens per 1 USD).
- **Deduction**: Real-time in the sense that `tokens_remaining` is derived from `gross_profit_usd` (from lending trade history) whenever stats are computed or user-status is fetched.
- **Depletion**: If `tokens_remaining < 0.1`, the bot stops (worker kill-switch) and start-bot returns 402 until the user upgrades or adds tokens.
- **Purchased tokens**: User can buy tokens (1 USD = 100 tokens) via Stripe; stored in `user_token_balance.purchased_tokens` and included in balance.
