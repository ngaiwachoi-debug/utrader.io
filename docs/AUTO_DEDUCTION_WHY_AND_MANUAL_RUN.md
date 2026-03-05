# Why auto token deduction might not run, and how to run it manually

## When does auto deduction run?

- **Time:** 10:30 UTC every day (configured by `DAILY_DEDUCTION_UTC_HOUR` / `DAILY_DEDUCTION_UTC_MINUTE` in `main.py`).
- **Requirement:** The **backend process must be running** at 10:30 UTC. The scheduler is an in-process asyncio task; if the server is stopped, restarted after 10:30, or not yet started at 10:30 UTC, the automatic run for that day will not happen.

## Why it didn't run today

Common reasons:

1. **Backend was not running at 10:30 UTC** – Server was stopped, redeployed, or started after 10:30 UTC.
2. **Backend restarted** – If uvicorn (or the app process) restarts, the scheduler starts again and waits until the *next* 10:30 UTC (e.g. tomorrow).
3. **Process crash before 10:30** – Any unhandled exception or OOM that kills the process before the run.

The backend logs at startup:  
`Auto token deduction runs only at 10:30 UTC when the backend is running. If the server is off at 10:30 UTC, deduction will not run; use Admin Panel → Deduction → Manual trigger or POST /admin/deduction/trigger to run it.`

When the scheduler wakes at 10:30 UTC it logs:  
`Daily token deduction: scheduler woke at ~10:30 UTC; starting deduction run.`

If you don't see that second log on the day in question, the server was not running at 10:30 UTC.

## How to run deduction manually (API)

**Option 1 – Admin UI**  
1. Log in to the admin panel as admin (e.g. ngaiwachoi@gmail.com).  
2. Open the **Deduction** section.  
3. Click **Manual trigger**.  
   - With default options this refreshes snapshots from Bitfinex (and 09:00 cache), then runs deduction so it’s correct even if the 10:00 run was missed.

**Option 2 – API**  
- **Endpoint:** `POST /admin/deduction/trigger`  
- **Query (optional):** `refresh_first=true` (default) – refresh snapshots from Bitfinex and 09:00 cache before deducting; use when 10:00 failed or server was down.  
- **Auth:** Admin JWT in `Authorization: Bearer <token>`.

Example (after obtaining an admin JWT):

```bash
curl -X POST "http://127.0.0.1:8000/admin/deduction/trigger?refresh_first=true" \
  -H "Authorization: Bearer YOUR_ADMIN_JWT"
```

Response: `{"status":"success","count":N,"entries":[...],"refreshed":M}`

## Logs to check

- **Startup:** `Auto token deduction runs only at 10:30 UTC when the backend is running...`
- **Each day (when waiting):** `Next daily token deduction at 10:30 UTC in Xs`
- **When it runs:** `Daily token deduction: scheduler woke at ~10:30 UTC; starting deduction run.` then per-user `token_deduction user_id=... gross_profit=... tokens_deducted=...`
- **If it fails after retries:** `Daily token deduction (10:30 UTC) failed after N retries: <error>`

If “scheduler woke” does not appear for a given date, the process was not running at 10:30 UTC that day; run it manually via the admin panel or the API above.
