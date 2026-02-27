# Deduction persistent run (no manual start/stop)

How to run the daily token deduction (and 09:40 gross-profit snapshot) **persistently**: auto-start with the backend, survive reboots, and recover from crashes without manual steps.

---

## How it works

- **09:40 UTC** and **10:15 UTC** jobs run **inside the FastAPI process** (in-process asyncio tasks started in `lifespan`).
- When you run the backend (e.g. `uvicorn main:app`), both schedulers start automatically.
- No separate cron or manual start/stop is required for the deduction system.
- To make this **persistent**, run the backend under a process manager (PM2, systemd, or Windows Service) and optionally a watchdog.

---

## 1. Deploy process manager / service

Choose one and follow its section.

### 1.1 PM2 (Linux / macOS)

**Use when:** You already use or prefer PM2 (Node.js process manager).

1. Install PM2: `npm install -g pm2`
2. From project root:
   ```bash
   pm2 start ecosystem.config.js
   ```
3. Persist across reboots:
   ```bash
   pm2 save
   pm2 startup
   ```
4. Useful commands:
   - `pm2 status` – list apps (utrader-api)
   - `pm2 logs utrader-api` – view logs
   - `pm2 restart utrader-api` – restart

**Config file:** `ecosystem.config.js` in project root. It starts `python -m uvicorn main:app --host 0.0.0.0 --port 8000` with autorestart. Load `.env` by running from project root (app loads it).

### 1.2 systemd (Linux)

**Use when:** You deploy on a Linux server and want a system service.

1. Edit `utrader.service`:
   - Set `User` and `Group` to your deploy user/group.
   - Set `WorkingDirectory` and `EnvironmentFile` to the real project path (e.g. `/var/www/utrader` or `/path/to/buildnew`).
2. Install and enable:
   ```bash
   sudo cp utrader.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl enable utrader
   sudo systemctl start utrader
   ```
3. Check:
   - `sudo systemctl status utrader` – running/stopped
   - `journalctl -u utrader -f` – follow logs

**Config file:** `utrader.service` in project root. Replace placeholders before install.

### 1.3 Windows Service

**Use when:** You run the backend on Windows and want it to start on boot.

**Option A – NSSM (recommended)**

1. Download NSSM from nssm.cc.
2. From an elevated prompt (project root):
   ```powershell
   nssm install UtraderAPI "C:\Path\To\python.exe" "-m uvicorn main:app --host 0.0.0.0 --port 8000"
   nssm set UtraderAPI AppDirectory "C:\path\to\buildnew"
   nssm start UtraderAPI
   ```
   Use your real Python path and project path. Ensure `.env` is in `AppDirectory` (app loads it).

**Option B – PowerShell script**

- Register: `.\scripts\utrader-service.ps1 -Register` (run as Administrator).
- Unregister: `.\scripts\utrader-service.ps1 -Unregister`
- Status: `.\scripts\utrader-service.ps1 -Status`

See `scripts/utrader-service.ps1` for details and the wrapper script it creates.

---

## 2. Watchdog (optional)

Use the watchdog only if the backend is **not** run by PM2/systemd/Windows Service (e.g. you start uvicorn by hand and want it restarted if it dies).

- **Bash:** Run periodically (e.g. cron every 1–5 min):
  ```bash
  chmod +x scripts/deduction_watchdog.sh
  # Cron: * * * * * /path/to/buildnew/scripts/deduction_watchdog.sh
  ./scripts/deduction_watchdog.sh
  ```
- **PowerShell:** Run via Task Scheduler every 1–5 min, or in a loop:
  ```powershell
  .\scripts\deduction_watchdog.ps1
  ```

Behavior: if `GET $API_BASE/openapi.json` fails, the script starts `uvicorn main:app` in the background. Logs go to `logs/deduction_watchdog.log` (and optionally uvicorn stdout/stderr).

---

## 3. How to check if the deduction scheduler is running

- The schedulers are **inside** the backend process. If the API is up, they are running.
- **Check API:**  
  `curl -s http://127.0.0.1:8000/openapi.json` (or your `API_BASE`) → 200 means backend (and thus 09:40/10:15 tasks) is running.
- **Check process:**
  - PM2: `pm2 list` → utrader-api online.
  - systemd: `systemctl status utrader` → active (running).
  - Windows: Task Manager or `Get-Service UtraderAPI` (if installed as service).

---

## 4. Logs for persistent execution

- **PM2:** `pm2 logs utrader-api`
- **systemd:** `journalctl -u utrader -f`
- **Windows (NSSM):** NSSM can redirect stdout/stderr to files; set in NSSM GUI or `nssm set UtraderAPI AppStdout ...`.
- **Watchdog:** `logs/deduction_watchdog.log` (and `logs/uvicorn.out.log` / `uvicorn.err.log` if the watchdog starts uvicorn).

Scheduler messages appear in the same backend log (e.g. "Next daily token deduction at 10:15 UTC in ...s", "Next daily gross profit refresh at ...").

---

## 5. Persistence validation steps

1. **Start backend with your process manager** (PM2 / systemd / Windows Service).
2. **Confirm API is up:** `curl -s http://127.0.0.1:8000/openapi.json` → 200.
3. **Reboot test (Linux/Windows):** Reboot the server; after boot, confirm the service/process is running and API returns 200. No manual start needed.
4. **Crash test:** Kill the backend process (e.g. `pm2 delete utrader-api` then `pm2 start ecosystem.config.js` again, or `systemctl kill utrader` then `systemctl start utrader`). Process manager should restart it; API should come back. If you use only the watchdog, run the watchdog script and confirm it starts uvicorn when the API is down.
5. **Schedule check:** Wait for 09:40 UTC and/or 10:15 UTC (or use `TEST_SCHEDULER_SECONDS` for an earlier first run) and confirm in logs that the 09:40 refresh and/or 10:15 deduction ran. No manual trigger required for normal operation.

---

## 6. Troubleshooting

| Issue | What to do |
|-------|------------|
| **Scheduler not starting** | Backend and schedulers start together. If the API is up, schedulers are running. Restart the backend (e.g. `pm2 restart utrader-api` or `systemctl restart utrader`). |
| **Backend exits immediately** | Check env (e.g. `DATABASE_URL`, Redis). Run manually: `python -m uvicorn main:app --host 0.0.0.0 --port 8000` and read the traceback. Fix config and redeploy. |
| **09:40/10:15 not running** | Confirm server timezone (UTC) and that the process has been up long enough for the next run. Check backend logs for scheduler messages. Use `TEST_SCHEDULER_SECONDS=30` to force a run 30s after startup for testing. |
| **Service won’t start on boot** | PM2: run `pm2 save` and `pm2 startup` and follow the printed command. systemd: `systemctl enable utrader`. Windows: confirm service is set to Automatic and NSSM/script paths are correct. |
| **Watchdog starts duplicate backends** | Run only one watchdog instance (e.g. one cron job or one scheduled task). If using PM2/systemd, the watchdog is redundant; you can disable it. |

---

## 7. Idempotence and compatibility

- **Idempotent:** Running the activation script or re-applying the same process-manager config multiple times does not create duplicate schedulers or services when used as documented.
- **Backward-compatible:** No changes to existing bot or API behavior. The 09:40 and 10:15 jobs are the same in-process tasks as before; only the way the backend process is started and kept running is configured for persistence.

---

## 8. Related docs

- **Execution and validation:** Fill in `docs/DEDUCTION_PERSISTENT_EXECUTION_REPORT.md` with script output, pass/fail per step, and confirmation that `DEDUCTION_AUTO_ACTIVATION_LOG.md` ends with **DEDUCTION ACTIVATED SUCCESSFULLY**.
- **No-manual-intervention guarantee:** See `docs/DEDUCTION_NO_MANUAL_INTERVENTION.md` for written confirmation that migrations are one-time, jobs run automatically on schedule, and the system recovers from crashes/reboots without human action.
