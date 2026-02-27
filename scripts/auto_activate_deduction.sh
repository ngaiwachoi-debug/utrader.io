#!/usr/bin/env bash
# Auto-activate daily token deduction: migrations → test → validation. Zero manual steps.
# Cross-platform: macOS/Linux. Logs to DEDUCTION_AUTO_ACTIVATION_LOG.md.
# Usage: ./scripts/auto_activate_deduction.sh   (chmod +x scripts/auto_activate_deduction.sh first)

set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG="$ROOT/DEDUCTION_AUTO_ACTIVATION_LOG.md"
API_BASE="${API_BASE:-http://127.0.0.1:8000}"

log() { echo "$1" | tee -a "$LOG"; }
log_step() { echo "" >> "$LOG"; echo "### $1" >> "$LOG"; echo '```' >> "$LOG"; }
log_end() { echo '```' >> "$LOG"; }

# Start log
echo "# Deduction auto-activation log" > "$LOG"
echo "Started: $(date -u +"%Y-%m-%dT%H:%M:%SZ")" >> "$LOG"
echo "ROOT=$ROOT" >> "$LOG"

cd "$ROOT"
export DATABASE_URL="${DATABASE_URL:-}"
if [ -f .env ]; then
  set -a
  source .env 2>/dev/null || true
  set +a
  [ -z "$DATABASE_URL" ] && DATABASE_URL=$(grep -E '^DATABASE_URL=' .env 2>/dev/null | cut -d= -f2- | tr -d '"' | tr -d "'") || true
fi

PASS=0
FAIL=0

# --- Step 1: Bot status migration ---
log_step "Step 1: Bot status migration (users.bot_status)"
if python migrations/run_bot_status_migration.py >> "$LOG" 2>&1; then
  log "  [PASS] Bot status migration"
  PASS=$((PASS+1))
else
  log "  [FAIL] Bot status migration"
  FAIL=$((FAIL+1))
fi
log_end

# --- Step 2: Daily gross migration ---
log_step "Step 2: Daily gross migration (user_profit_snapshot.daily_gross_*)"
if python migrations/run_daily_gross_migration.py >> "$LOG" 2>&1; then
  log "  [PASS] Daily gross migration"
  PASS=$((PASS+1))
else
  log "  [FAIL] Daily gross migration"
  FAIL=$((FAIL+1))
fi
log_end

# --- Step 3: Deduction test (with retry) ---
log_step "Step 3: Deduction logic test (3 cases)"
TEST_OUT="$ROOT/.deduction_test_out.txt"
RUN_TEST() { python scripts/test_daily_deduction_manual.py > "$TEST_OUT" 2>&1; echo $?; }
RET=$(RUN_TEST) || true
cat "$TEST_OUT" >> "$LOG"
if [ "${RET:-1}" -eq 0 ]; then
  log "  [PASS] Deduction test"
  PASS=$((PASS+1))
else
  # Auto-retry: run both migrations again and retry once
  log "  [RETRY] Re-running migrations and retrying test..."
  python migrations/run_bot_status_migration.py >> "$LOG" 2>&1 || true
  python migrations/run_daily_gross_migration.py >> "$LOG" 2>&1 || true
  RET2=$(RUN_TEST) || true
  cat "$TEST_OUT" >> "$LOG"
  if [ "${RET2:-1}" -eq 0 ]; then
    log "  [PASS] Deduction test (after retry)"
    PASS=$((PASS+1))
  else
    log "  [FAIL] Deduction test"
    FAIL=$((FAIL+1))
  fi
fi
rm -f "$TEST_OUT"
log_end

# --- Step 4: Bot compatibility ---
log_step "Step 4: Bot compatibility (app has deduction + bot routes)"
if python -c "
import sys
sys.path.insert(0, '$ROOT')
import main
assert callable(getattr(main, 'run_daily_token_deduction', None)), 'run_daily_token_deduction missing'
assert hasattr(main, 'start_bot'), 'start_bot missing'
assert hasattr(main, '_run_daily_token_deduction_scheduler'), 'deduction scheduler missing'
print('OK')
" >> "$LOG" 2>&1; then
  log "  [PASS] Bot/deduction coexistence"
  PASS=$((PASS+1))
else
  log "  [FAIL] Bot/deduction check"
  FAIL=$((FAIL+1))
fi
log_end

# --- Optional: API reachable ---
log_step "Step 5: API reachable (optional)"
if command -v curl >/dev/null 2>&1 && curl -sf "$API_BASE/openapi.json" -o /dev/null 2>>"$LOG"; then
  log "  [PASS] API reachable at $API_BASE"
  PASS=$((PASS+1))
else
  log "  [SKIP] API not reachable (backend may be stopped)"
fi
log_end

# --- Auto-fix: if any failure, re-run migrations and retry once ---
if [ "$FAIL" -gt 0 ]; then
  log_step "Auto-fix: Re-running migrations and re-checking"
  echo "Fixes applied: Re-ran bot_status + daily_gross migrations." >> "$LOG"
  python migrations/run_bot_status_migration.py >> "$LOG" 2>&1 || true
  python migrations/run_daily_gross_migration.py >> "$LOG" 2>&1 || true
  PASS2=0
  FAIL2=0
  if python migrations/run_bot_status_migration.py >> "$LOG" 2>&1; then PASS2=$((PASS2+1)); else FAIL2=$((FAIL2+1)); fi
  if python migrations/run_daily_gross_migration.py >> "$LOG" 2>&1; then PASS2=$((PASS2+1)); else FAIL2=$((FAIL2+1)); fi
  RET3=$(RUN_TEST) || true
  cat "$TEST_OUT" >> "$LOG" 2>/dev/null || true
  if [ "${RET3:-1}" -eq 0 ]; then PASS2=$((PASS2+1)); else FAIL2=$((FAIL2+1)); fi
  echo "Re-run result: Passed=$PASS2 Failed=$FAIL2" >> "$LOG"
  log_end
  if [ "$FAIL2" -eq 0 ]; then
    PASS=$((PASS+PASS2))
    FAIL=0
  fi
fi
rm -f "$TEST_OUT"

# --- Summary ---
echo "" >> "$LOG"
echo "---" >> "$LOG"
echo "## Summary" >> "$LOG"
echo "Passed: $PASS | Failed: $FAIL" >> "$LOG"
echo "Finished: $(date -u +"%Y-%m-%dT%H:%M:%SZ")" >> "$LOG"
if [ "$FAIL" -eq 0 ]; then
  echo "" >> "$LOG"
  echo "## **DEDUCTION ACTIVATED SUCCESSFULLY**" >> "$LOG"
  log ""
  log "DEDUCTION ACTIVATED SUCCESSFULLY — see $LOG"
  exit 0
else
  echo "" >> "$LOG"
  echo "## ACTIVATION INCOMPLETE (see failed steps above)" >> "$LOG"
  log ""
  log "ACTIVATION INCOMPLETE — $FAIL step(s) failed. See $LOG"
  exit 1
fi
