# Bot Lifecycle Validation Report

Use this checklist to record pass/fail for production readiness. Run the automated script first, then complete manual tests.

## Automated script

```bash
# Bash (Linux/macOS)
./scripts/test_bot_lifecycle.sh

# PowerShell (Windows)
.\scripts\test_bot_lifecycle.ps1
```

**Prerequisites**: Backend running with `ALLOW_DEV_CONNECT=1`; ARQ worker running; `API_BASE` set if not `http://127.0.0.1:8000`.

---

## Test results (fill in Pass/Fail and notes)

| # | Test | Pass/Fail | Notes |
|---|------|-----------|--------|
| 1 | Register + API keys → auto-start (valid keys) | | Within ~15s Terminal shows logs, Live Status Running |
| 2 | Terminal logs (2s polling) | | Log lines appear and refresh |
| 3 | Stop Bot | | Badge shows Stopped; logs stop |
| 4 | Start Bot again after stop | | Bot restarts; no "already running" error |
| 5 | No regressions (tokens, subscription, deposit) | | Token endpoint and Settings work |
| 6 | Invalid Bitfinex API keys → bot does NOT auto-start | | 400 response; no bot start; logs "invalid API keys" or similar |
| 7 | Multiple Start/Stop clicks → idempotent | | No race conditions; status consistent |
| **Script** | test_bot_lifecycle.sh / .ps1 | | All steps PASS |

---

## Token endpoint check (no regression)

The test script calls `GET /user-status/{user_id}` with JWT and asserts `tokens_remaining` is present. If this fails, bot changes may have affected token or auth paths.

- **Pass**: user-status returns 200 with `tokens_remaining`.
- **Fail**: Fix token/auth before release.

---

## Sign-off

- [ ] DB migration applied (`bot_status` column exists).
- [ ] Automated script: all steps pass.
- [ ] Manual tests 1–7 completed and recorded above.
- [ ] No breaking API changes; frontend backward compatible.

**Date**: _______________  
**Environment**: _______________
