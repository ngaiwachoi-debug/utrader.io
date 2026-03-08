# Fix: Restart Issues and Logs – What’s Wrong and How to Fix

## 1. What the logs show (Terminal 1)

The open terminal (`terminals/1.txt`) is running **Stripe CLI** (`stripe listen --forward-to http://127.0.0.1:8000/webhook/stripe`). It also shows:

### PowerShell PSReadLine crash when pasting

```
Oops, something went wrong.  Please report this bug with the details below.
Report on GitHub: https://github.com/lzybkr/PSReadLine/issues/new
Exception:
System.ArgumentOutOfRangeException: The value must be greater than or equal to zero.
Parameter name: top
Actual value was -1.
   at System.Console.SetCursorPosition(Int32 left, Int32 top)
   at Microsoft.PowerShell.PSConsoleReadLine.ReallyRender(...)
   at Microsoft.PowerShell.PSConsoleReadLine.Paste(...)
```

**What’s wrong:** PSReadLine (PowerShell’s line editor) is calling `SetCursorPosition` with `top = -1`. That usually happens when the console buffer/window state is inconsistent (e.g. after paste, resize, or rapid output).

**Plan to fix / work around:**

| Option | Action |
|--------|--------|
| **A. Avoid paste in that window** | Type commands instead of pasting in the Stripe terminal, or paste in a different terminal. |
| **B. Resize the window** | Before pasting, resize the PowerShell window slightly so the internal cursor position is recalculated. |
| **C. Use a different terminal** | Run `stripe listen` in Windows Terminal or CMD instead of PowerShell, or in a separate VS Code terminal. |
| **D. Update PSReadLine** | `Update-Module PSReadLine` (run as admin or for current user). Newer versions may have fixes. |
| **E. Disable PSReadLine for that session** | Start PowerShell with `powershell -NoProfile` or temporarily remove/rename the PSReadLine module so the paste path isn’t used. |

This is an environment/tooling issue, not an application bug. Your app and Stripe webhooks (all 200 in the log) are fine.

---

## 2. If “restarted twice” means the ARQ worker (bot still not working)

If you restarted the **ARQ worker** twice and the bot still fails (e.g. “Could not fetch wallets” or no orders), use this checklist.

### 2.1 Confirm the worker is running the fixed code

- In `bot_engine.py`, `PortfolioManager._api_request` must **not** call `get_next_nonce`; it must use only `self._nonce` (in-memory).  
- Current code in this repo already does that. So the worker must be started **after** saving that code and from the **project root** so it loads this `bot_engine.py`.

### 2.2 One worker, one job per user

- Run only **one** ARQ worker process (e.g. one terminal with `python scripts/run_worker.py`).  
- Before starting the bot, **stop** it once (UI or `POST /stop-bot/2`), wait ~5–10 s, then **start** again. That avoids multiple queued jobs for user 2 and reduces 10114 “nonce: small” when the same key is used from several jobs.

### 2.3 Restart sequence that works

1. Stop the bot for user 2 (UI or API).
2. Stop the worker (Ctrl+C in the worker terminal).
3. Start the worker: `cd c:\Users\choiw\Desktop\bifinex\buildnew` then `python scripts/run_worker.py`.
4. Wait until you see “Starting worker for 1 functions: run_bot_task”.
5. Start the bot for user 2 (UI or API).
6. In the **worker terminal** you should see “Found 2 funding wallet(s)” and then “TICKET ISSUED” lines.  
   In the dashboard terminal tab you may see the same, or “Could not fetch wallets” if an earlier job (from before restart) is still in the log.

### 2.4 If it still fails after this

- In the **worker process** stdout (the window where `run_worker.py` is running), look for either:
  - `[User 2] [SCANNER] Bitfinex /auth/r/wallets API error: [...]`  
  - or `[User 2] [SCANNER] Failure: Could not fetch wallets: <Exception>: ...`  
- That line tells you the real cause (e.g. 10114, network, key, etc.).  
- If the dashboard “Trading terminal” never shows “Found … funding wallet(s)” but the worker stdout does, the fix is working and the UI is likely showing an older or mixed log; rely on the worker stdout.

---

## 3. Summary

| Problem | Log / symptom | Fix / plan |
|--------|----------------|------------|
| **PowerShell crash when pasting** | PSReadLine `ArgumentOutOfRangeException`, `top = -1` in Terminal 1 | Use Options A–E above (avoid paste there, resize, different terminal, update PSReadLine, or disable it). |
| **Worker “restarted twice” but bot still not working** | No worker log in Terminal 1 (that’s Stripe). Need worker terminal or dashboard bot log. | Follow §2: one worker, stop-then-start bot, confirm worker stdout shows “Found 2 funding wallet(s)” and “TICKET ISSUED”. If not, use the new error line in worker stdout to see exact cause. |

Stripe in the log is healthy (all webhook POSTs 200). For the bot, the code path is fixed; the remaining issues are environment (PSReadLine) and/or restart/worker/job discipline (one worker, clean stop/start).
