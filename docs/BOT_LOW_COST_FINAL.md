# Bot Logic and Low-Cost Execution (Final)

## Product rules

- **Token gating:** Bot runs only when `tokens_remaining >= 1`. If balance drops below 1, the worker stops the bot (terminal message, set `bot_status = "stopped"`).
- **First-time API key save:** When a user saves Bitfinex API keys for the **first time** (vault did not exist before), they receive a **150-token** balance row (if none exists) and the bot is **auto-started** only if `tokens_remaining >= 1`. Subsequent key updates do **not** auto-start the bot.
- **Manual Start:** If the user clicks Start and `tokens_remaining < 1`, the backend returns **400** with `code: "INSUFFICIENT_TOKENS"` and `redirect_tab: "subscription"`. The frontend shows the message and a button to open the Subscription tab.
- **Stop:** Unchanged; Stop cancels the running task as before.

## Tier rebalance intervals (worker)

| Tier     | Rebalance interval |
|----------|---------------------|
| Trial    | 240 min (4h)        |
| Free     | 240 min (4h)        |
| Pro      | 5 min               |
| AI Ultra | 30 min              |
| Whales   | 10 min              |

`plan_tier` from the DB is normalized (e.g. `"ai ultra"` → `ai_ultra`) when looking up config.

## Terminal (Redis) cost controls

- **Line cap:** Terminal log list is trimmed to the last **300** lines (`ltrim -300`).
- **Batching:** Terminal logs are flushed to Redis:
  - Once shortly after start (~15s) so “Bot started” appears quickly.
  - Every **90 seconds** via a periodic task.
  - On each kill-switch loop wake-up (at rebalance interval).
- Aggressive per-second early flushes were removed.

## Frontend polling

- **Bot status (`/bot-stats`):** Poll interval **90 seconds** (was 5s).
- **Terminal tab:**
  - For the **first 5 minutes** after the user has triggered Start (or the tab sees bot starting/running), poll every **10 seconds**.
  - After that, **tier-based** poll interval:
    - Trial/Free: 4h (14400000 ms)
    - Pro: 5 min (300000 ms)
    - AI Ultra: 30 min (1800000 ms)
    - Whales: 10 min (600000 ms)

## Redis cost summary

Target ~$150–250/mo by reducing write frequency (terminal batch 90s, 300-line cap), and read frequency (bot-stats 90s, terminal tier-based + 10s for first 5 min).

## Restart after deploy

After deploying these changes, restart:

1. **Backend** (e.g. uvicorn)
2. **ARQ worker(s)** (e.g. `run_worker.py`)
3. **Frontend** (Next.js)

so new intervals and token-gating behavior take effect everywhere.
