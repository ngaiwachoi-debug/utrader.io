# Bot Plan: Test Result and Follow-Up

## Test Executed

1. **ARQ worker restarted** in background (loads `bot_engine.py` with in-memory nonce only, no Redis nonce in worker path).
2. **Stop bot for user 2** via API (`POST /stop-bot/2`).
3. **Start bot for user 2** via API (`POST /start-bot/2`).
4. **Terminal logs** were read via `GET /terminal-logs/2` after 35s and from the **worker process stdout**.

## Result: Orders Are Placing

The **worker stdout** (the process that runs the fixed code) shows:

- Scanner: `[User 2] [SCANNER] Found 2 funding wallet(s). Starting trading engines...`
- Engines: `Omni-Node Initialized | UST`, `Omni-Node Initialized | USD`
- Deploy: `[USD] Available = 89,889.9893`, `[UST] Available = 102,650.0656`, `Deploying`, `Grid Available`
- Many **TICKET ISSUED** lines for SENIOR, MEZZANINE, and TAIL TRAP (USD and UST).

So when the worker runs the current `bot_engine.py` (no Redis nonce in worker path), **user 2 can place orders**. The earlier “Could not fetch wallets” was due to the worker using Redis nonce with ARQ’s Redis; that has been removed.

The test script’s `GET /terminal-logs/2` returned 38 lines that mixed several jobs and did not show TICKET ISSUED in that slice; the worker’s own stdout is the source of truth and shows orders placing.

---

## Remaining Issues (Follow-Up Plan)

These do not stop the bot from placing orders but are worth fixing next.

### 1. Multiple jobs for the same user (10114 “nonce: small”)

When more than one `run_bot_task(2)` runs (e.g. retries or duplicate enqueues), they share the same Bitfinex API key and different in-memory nonces, so Bitfinex can return `10114 "nonce: small"` for wallet/credits/offer calls.

**Follow-up:**

- Ensure **only one bot job per user** when starting: e.g. in `main.py` when enqueueing, call `job.abort()` for the existing `bot_user_{user_id}` job (if any) and wait briefly before enqueueing the new one, so only one run_bot_task runs at a time.
- Optionally, in the worker, **early exit** when `bot_desired_state == "stopped"` is already implemented; keep it so any stale/duplicate jobs exit quickly and don’t compete on nonce.

### 2. UST TAIL TRAP 10001 “minimum is 150.0”

Worker stdout shows:

`[User 2] API /auth/w/funding/offer/submit → HTTP 500 | ["error",10001,"Invalid offer: incorrect amount, minimum is 150.0 dollar or equivalent in UST"]`  
`└─ [UST] SUBMIT FAILED | TAIL TRAP | amount=150.0000`

Bitfinex rejects exactly **150.0** for UST (likely requires strictly > 150 or 150.01).

**Follow-up (already designed in fix_10001_minimum_amount_only plan):**

- In `bot_engine.py` `deploy_matrix`, define **MIN_SUBMIT_AMOUNT = 150.01** (or `MIN_ORDER_USD + 0.01`).
- After computing `order_amt` and before appending to `ops`, if `order_amt >= MIN_ORDER_AMT` and `order_amt < 150.01` and `running_balance >= 150.01`, set `order_amt = 150.01` for all three tranches (Senior, Mezzanine, Tail).
- No Redis/nonce changes; scanner remains as-is.

### 3. Test script vs worker stdout

The automated test (`test_bot_stop_start_logs.py`) uses `GET /terminal-logs/2`, which can return a limited or interleaved set of lines from Redis. To assert “orders placing” reliably, either:

- Lengthen the wait (e.g. 55s) and/or
- Have the test also consider worker stdout, or
- Ensure only one job runs so terminal_logs are dominated by a single run and “TICKET ISSUED” appears in the fetched lines.

---

## Summary

- **Current state:** With the worker using the updated `bot_engine.py` (in-memory nonce only, no Redis nonce in worker path), the scanner succeeds and **user 2 can place orders** (TICKET ISSUED for SENIOR, MEZZANINE, TAIL TRAP).
- **Follow-up plan:** (1) Enforce single job per user to reduce 10114; (2) Add MIN_SUBMIT_AMOUNT 150.01 in `deploy_matrix` to fix UST TAIL TRAP 10001; (3) Optionally adjust the test so it reliably verifies TICKET ISSUED (longer wait or single-job guarantee).
