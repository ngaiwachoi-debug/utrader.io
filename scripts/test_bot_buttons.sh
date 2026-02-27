#!/usr/bin/env bash
# Validation for fixed Start/Stop Bot buttons and auto-start.
# Requires: backend (ALLOW_DEV_CONNECT=1), ARQ worker. Optional: BFX_KEY/BFX_SECRET.
# Usage: ./scripts/test_bot_buttons.sh

set -e
API_BASE="${API_BASE:-http://127.0.0.1:8000}"
BFX_KEY="${BFX_KEY:-}"
BFX_SECRET="${BFX_SECRET:-}"
EMAIL="bot-buttons-test-$(date +%s)@gmail.com"
WAIT_START=30
POLL=2
PASS=0
FAIL=0

pass() { echo "  [PASS] $1"; PASS=$((PASS+1)); }
fail() { echo "  [FAIL] $1 — $2"; FAIL=$((FAIL+1)); }

echo "--- Bot Buttons Validation ---"
echo "API_BASE=$API_BASE  EMAIL=$EMAIL"

echo "1. Backend health"
curl -sf "$API_BASE/openapi.json" -o /dev/null && pass "Backend reachable" || { fail "Backend" "unreachable"; exit 1; }

echo "2. Create test user"
CREATE=$(curl -s -X POST "$API_BASE/dev/create-test-user" -H "Content-Type: application/json" -d "{\"email\":\"$EMAIL\"}")
USER_ID=$(echo "$CREATE" | sed -n 's/.*"user_id": *\([0-9]*\).*/\1/p')
[ -n "$USER_ID" ] || { fail "Create user" "$CREATE"; exit 1; }
pass "Create test user (user_id=$USER_ID)"

echo "3. Get JWT"
LOGIN=$(curl -s -X POST "$API_BASE/dev/login-as" -H "Content-Type: application/json" -d "{\"email\":\"$EMAIL\"}")
TOKEN=$(echo "$LOGIN" | sed -n 's/.*"token":"\([^"]*\)".*/\1/p')
[ -n "$TOKEN" ] || { fail "JWT" "$LOGIN"; exit 1; }
pass "Get JWT"

echo "4. Connect API keys (set BFX_KEY/BFX_SECRET for auto-start)"
if [ -n "$BFX_KEY" ] && [ -n "$BFX_SECRET" ]; then
  CONNECT=$(curl -s -X POST "$API_BASE/connect-exchange" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" -d "{\"bfx_key\":\"$BFX_KEY\",\"bfx_secret\":\"$BFX_SECRET\"}")
  echo "$CONNECT" | grep -q '"status".*"success"' && pass "Connect exchange" || fail "Connect" "check keys"
else
  echo "   Skipping (set BFX_KEY and BFX_SECRET for real keys)"
fi

echo "5. Start Bot"
START1=$(curl -s -X POST "$API_BASE/start-bot" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json")
echo "$START1" | grep -q '"status".*"success"' && pass "Start Bot success" || fail "Start Bot" "$START1"

echo "6. Poll until active"
ACTIVE="false"
for _ in $(seq 1 $((WAIT_START/POLL))); do
  sleep $POLL
  BOTSTAT=$(curl -s -H "Authorization: Bearer $TOKEN" "$API_BASE/bot-stats/$USER_ID")
  echo "$BOTSTAT" | grep -q '"active":true' && { pass "Bot active"; ACTIVE="true"; break; }
done
[ "$ACTIVE" = "true" ] || fail "Bot active" "timeout"

echo "7. Stop Bot"
STOP=$(curl -s -X POST "$API_BASE/stop-bot" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json")
echo "$STOP" | grep -q '"status".*"success"' && pass "Stop Bot success" || fail "Stop Bot" "$STOP"
sleep 3
BOTSTAT=$(curl -s -H "Authorization: Bearer $TOKEN" "$API_BASE/bot-stats/$USER_ID")
echo "$BOTSTAT" | grep -q '"active":false' && pass "Bot stopped" || fail "Stopped" "still active"

echo "8. Start again"
START2=$(curl -s -X POST "$API_BASE/start-bot" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json")
echo "$START2" | grep -q '"status".*"success"' && pass "Start again success" || fail "Start again" "$START2"

echo "9. Duplicate Start (idempotent)"
START3=$(curl -s -X POST "$API_BASE/start-bot" -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json")
echo "$START3" | grep -q '"status".*"success"' && pass "Duplicate Start success" || fail "Duplicate Start" "$START3"

echo "10. Terminal logs"
LOGS=$(curl -s -H "Authorization: Bearer $TOKEN" "$API_BASE/terminal-logs/$USER_ID")
echo "$LOGS" | grep -q '"lines"' && pass "terminal-logs OK" || fail "Terminal logs" "no lines"

echo ""
echo "--- Result: $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ]
