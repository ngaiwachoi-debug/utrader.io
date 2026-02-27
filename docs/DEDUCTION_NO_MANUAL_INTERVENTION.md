# No-manual-intervention guarantee (deduction system)

Written confirmation of how the deduction system runs without manual steps.

---

## 1. Migrations

- Migrations (bot_status, daily_gross) are **applied once** (by the auto-activation script or manually).
- They are **idempotent**: safe to run multiple times; "column already exists" is treated as success.
- After activation, **no manual re-run of migrations** is required for normal operation.

---

## 2. Deduction jobs (09:40 and 10:15 UTC)

- **Start:** The 09:40 gross-profit snapshot and 10:15 token deduction run **automatically** when the backend server starts (FastAPI lifespan).
- **Schedule:** They run on their UTC schedule every day with **no manual start/stop**.
- **No cron needed:** When the backend is run via uvicorn (or under PM2/systemd/Windows Service), both jobs are active; no separate cron or task is required for the deduction system.

---

## 3. Recovery from crashes and reboots

- **Crashes:** When using a process manager (PM2, systemd, Windows Service), the backend restarts automatically on crash; the schedulers start again with the process. **No human action** is required.
- **Reboots:** When the service is enabled (e.g. `pm2 startup`, `systemctl enable utrader`, or Windows Service set to Automatic), the backend starts on boot and the deduction system runs again **without manual intervention**.
- **Retries:** The 10:15 deduction job retries up to 3 times at 5-minute intervals on failure; no manual retry is required.

---

## 4. Watchdog (optional)

- If you use the provided watchdog script (e.g. cron or Task Scheduler), it **monitors** the backend and **starts** it if it is not reachable. This is for environments where a process manager is not used; it does not replace PM2/systemd/Windows Service when those are in use.

---

## 5. Summary

- **Migrations:** One-time (idempotent); no ongoing manual re-run.
- **Daily jobs:** Start with the backend; run on schedule (09:40 and 10:15 UTC) without manual start/stop.
- **Crashes/reboots:** Handled by process manager (and optional watchdog) so the system recovers without human action.
- **Backward compatibility:** No breaking changes to bot or API; existing behavior is preserved.
