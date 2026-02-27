# Redis Migration Guide (NEW Upstash Server)

Migrate from the old Upstash account to the **NEW** Redis server with zero downtime and no regressions.

---

## 1. New Redis server

- **Host:** `eminent-antelope-62080.upstash.io`
- **Scheme:** `rediss://` (SSL/TLS required)
- **Config:** Set `REDIS_URL` in `.env` only (no hardcoded credentials in code).

Example (replace with your actual password from Upstash console):

```env
REDIS_URL="rediss://default:YOUR_PASSWORD@eminent-antelope-62080.upstash.io:6379"
```

---

## 2. Step-by-step migration

### 2.1 Update `.env`

1. Open `.env` in the project root.
2. Set `REDIS_URL` to the **new** Upstash connection string (`rediss://...`).
3. Optionally comment the old `REDIS_URL` line for rollback:
   ```env
   # REDIS_URL="rediss://...@fancy-kit-48774.upstash.io:6379"
   ```

### 2.2 Restart services (minimal downtime)

1. **Backend:** Restart the FastAPI process (e.g. `uvicorn main:app` or PM2/systemd).
   - On startup you should see: `Connected to Redis server at eminent-antelope-62080.upstash.io (queue + deduction)`.
2. **ARQ worker:** Restart the worker so it uses the new `REDIS_URL`:
   ```bash
   python scripts/run_worker.py
   ```
   - You should see: `Starting ARQ worker (Redis: eminent-antelope-62080.upstash.io). Ctrl+C to stop.`

### 2.3 Verify

1. **Redis connectivity:**
   ```bash
   python scripts/test_upstash_redis.py
   ```
   Expect: `[PASS] Redis connected at eminent-antelope-62080.upstash.io (ping OK)`.

2. **Migration script:**
   ```bash
   ./scripts/test_new_redis_migration.sh   # Bash
   .\scripts\test_new_redis_migration.ps1 # PowerShell
   ```

3. **Bot start/stop:** Run `python scripts/validate_bot_buttons_local.py` and confirm Step 2 (Start Bot) returns 200.

4. **Token deduction:** 09:40 / 10:15 UTC jobs use the same Redis via the backend; no separate config. Optional: use `TEST_SCHEDULER_SECONDS=30` and check logs for deduction.

---

## 3. Rollback (emergency)

If you need to revert to the old Upstash server:

1. In `.env`, comment the new `REDIS_URL` and uncomment the old one.
2. Restart the backend and the ARQ worker.
3. Re-run the validation script to confirm.

---

## 4. Troubleshooting

| Issue | What to do |
|-------|------------|
| **SSL errors** | Ensure `REDIS_URL` uses `rediss://` (double s). ARQ/redis-py set `ssl=True` from the scheme. |
| **Connection timeout** | Check firewall and network; confirm the new Upstash host is reachable from the server. |
| **503 on Start Bot** | Run `python scripts/test_upstash_redis.py`. If it fails, fix `REDIS_URL` (typos, host, password). |
| **Worker not picking up jobs** | Restart the worker after changing `.env`; ensure the worker process loads the same `.env` (run from project root). |
| **Old host still in use** | Search the repo for `fancy-kit-48774`; remove from code. Keep only in `.env` as a commented rollback line if desired. |

---

## 5. Compatibility

- **Bot start/stop:** Uses the same ARQ queue on the new Redis; no code change beyond `REDIS_URL`.
- **Daily deduction (09:40 / 10:15):** In-process in the backend; backend uses `REDIS_URL` for any Redis usage (e.g. caching). No separate Redis config for deduction.
- **Token Balance API:** No Redis dependency; unchanged.
- **Admin panel:** Any future Redis usage should read `REDIS_URL` from env; no changes needed for this migration.
