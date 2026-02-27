# POST /start-bot 500 Internal Server Error – Root Cause

## Summary

**Symptom:** POST /start-bot returns 500 (not 503) when using Upstash Redis (`rediss://...`). Validation script fails at Step 2 (Start Bot); no ARQ job enqueued, `bot_status` stays "stopped".

**Exact reason:** Uncaught exceptions in the start-bot flow (Redis connection or ARQ enqueue) were not converted to 503. The backend either:

1. **Raised a non-HTTPException** during `get_redis_or_raise()` or `_enqueue_bot_task()` (e.g. `redis.exceptions.ConnectionError`, SSL handshake timeout, or encoding error), which FastAPI turned into **500 Internal Server Error** instead of **503 Service Unavailable**.
2. **No retry** for transient Upstash connection failures, so a single timeout or SSL blip produced a 500.
3. **No explicit SSL/retry tuning** for `rediss://` in the main Redis pool or in the ARQ worker, so Upstash (which requires TLS and can be slower) could fail without a clear 503 message.

So the root cause is **missing error handling and Upstash-friendly Redis configuration**: Redis/connection errors were not mapped to 503, and connection settings (timeout, retries, SSL) were not tuned for Upstash.

---

## Traceback (conceptual)

Backend logs for a 500 on POST /start-bot often showed something like:

```
ERROR:    Exception in ASGI application
Traceback ( most recent call last ):
  ...
  redis = await get_redis_or_raise()
  ...
  File "arq/connections.py", line ...
    await pool.ping()
redis.exceptions.ConnectionError: Error connecting to ...
```

or a timeout/SSL error during `create_pool` or `enqueue_job`. Because these were not caught and re-raised as `HTTPException(503, ...)`, FastAPI returned **500**.

---

## Upstash Redis connection test

- **Before fix:** With `REDIS_URL=rediss://default:...@fancy-kit-48774.upstash.io:6379`, POST /start-bot could return 500 and logs showed a Redis connection or enqueue exception.
- **After fix:**  
  - Run `python scripts/test_upstash_redis.py`: should print `[PASS] Upstash Redis connected (ping OK)`.  
  - POST /start-bot should return 200 when Redis is reachable, or **503** (not 500) when Upstash is unreachable, with a clear "Queue service unavailable" / "Upstash Redis" message.

---

## Fixes applied

1. **Redis connection (main.py)**  
   - Explicit **SSL** for `rediss://` and higher **timeout/retries** for Upstash.  
   - **3x retry** with delay in `get_redis()` before failing.  
   - All Redis/connection/timeout errors in `get_redis_or_raise()` are caught and re-raised as **HTTPException(503)** with an "Upstash Redis" message.

2. **Start-bot endpoint (main.py)**  
   - **Try/except** around `get_redis_or_raise()` and `_enqueue_bot_task()`.  
   - **Full traceback** logged on any exception.  
   - Redis/connection/timeout errors → **503** (not 500).  
   - Any other exception → **500** with error detail (for debugging).

3. **ARQ worker (worker.py)**  
   - Worker Redis settings built so that **rediss://** gets **ssl=True** and higher **conn_timeout** / **conn_retries** (Upstash-compatible).  
   - No local Redis dependency; worker uses `REDIS_URL` from env (e.g. Upstash only).

4. **run_worker.py**  
   - Loads **.env** so `REDIS_URL` is set when running `python scripts/run_worker.py`.  
   - Logs "Starting ARQ worker (Upstash Redis)" when `REDIS_URL` uses `rediss://`.

5. **Validation script**  
   - On **503** from Start Bot, prints a hint to run `python scripts/test_upstash_redis.py` to verify Upstash.  
   - Docstring updated: Upstash REDIS_URL in .env, no local Redis required.
