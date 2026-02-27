# Fixed Upstash Bot Buttons – Validation Guide

## How to apply the fix

1. **Replace/update files** (already applied in repo):
   - **main.py:** Redis connection with SSL for `rediss://`, 3x retry, and `get_redis_or_raise()` mapping all Redis/connection errors to 503. Start-bot endpoint wrapped in try/except: enqueue failures logged with full traceback, Redis-related errors → 503, others → 500 with detail.
   - **worker.py:** `_worker_redis_settings()` so `rediss://` gets `ssl=True` and higher timeouts/retries.
   - **scripts/run_worker.py:** Load `.env`, log "Upstash Redis" when `REDIS_URL` uses `rediss://`.
   - **scripts/validate_bot_buttons_local.py:** 503 from Start Bot triggers a hint to run `scripts/test_upstash_redis.py`.
   - **scripts/test_upstash_redis.py:** New script to test Upstash Redis connection (ping).

2. **Restart services:**
   - Restart the FastAPI backend (so it uses the new Redis/error handling).
   - Restart the ARQ worker: `python scripts/run_worker.py` (from project root; .env with REDIS_URL is loaded).

3. **No local Redis:** Use only Upstash; set `REDIS_URL=rediss://...` in `.env`.

---

## How to test Upstash Redis connection

From project root:

```bash
python scripts/test_upstash_redis.py
```

- **Success:** `[PASS] Upstash Redis connected (ping OK)` and "Upstash Redis ready."
- **Failure:** `[FAIL] Upstash Redis connection failed: ...` → check REDIS_URL, network, and Upstash dashboard.

---

## How to re-run validation (confirm Step 2 passes)

From project root:

```bash
python scripts/validate_bot_buttons_local.py
```

- Ensure backend and ARQ worker are running (with same REDIS_URL in .env).
- Step 1: Backend health should pass.
- **Step 2: Start Bot** should return 200 and "Start Bot success" (no 500). If you get 503, run `python scripts/test_upstash_redis.py` and fix REDIS_URL/network.

---

## How to verify bot starts/stops with Upstash (no local Redis)

1. Set only `REDIS_URL=rediss://default:...@....upstash.io:6379` in `.env` (no local redis-server).
2. Start backend: `uvicorn main:app --host 0.0.0.0 --port 8000` (or your usual command).
3. Start worker: `python scripts/run_worker.py` → should log "Starting ARQ worker (Upstash Redis)."
4. In the UI (or via API): click **Start Bot** → should succeed (200); **Stop Bot** → should succeed. No 500 from POST /start-bot.

---

## Troubleshooting Upstash

| Issue | What to do |
|-------|------------|
| **503 on Start Bot** | Run `python scripts/test_upstash_redis.py`. If it fails, fix REDIS_URL (typos, correct host/port/password), firewall, and Upstash dashboard (e.g. suspend/restore). |
| **REDIS_URL typos** | Ensure `rediss://` (double s), correct username (often `default`), password and host from Upstash console. No spaces or line breaks in .env. |
| **SSL errors** | Backend and worker now set `ssl=True` for `rediss://`. If you still see SSL errors, check Python and system CA certs. |
| **500 (not 503)** | Check backend logs for the full traceback (we log it). If it’s a Redis/connection error, we should map it to 503; if you still get 500, the traceback will show the real cause. |
| **Worker not picking up jobs** | Ensure the worker is started **after** loading .env (e.g. `python scripts/run_worker.py` from project root). Same REDIS_URL as backend. |

---

## Compatibility

- **Daily token deduction (09:40/10:15):** Unchanged; they run in the FastAPI process and do not use the ARQ queue. No impact from Upstash Redis for the deduction jobs.
- **Token Balance API:** Unchanged; no Redis dependency.
- **Admin panel:** No change; future admin features can keep using the same REDIS_URL for queue/workers.
