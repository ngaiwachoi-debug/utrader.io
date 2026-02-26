#!/usr/bin/env bash
# Bot lifecycle E2E: register user, invalid keys (no auto-start), manual start, stop, start, logs, token endpoint.
# Requires: backend with ALLOW_DEV_CONNECT=1; ARQ worker for bot logs.
# Usage: ./scripts/test_bot_lifecycle.sh   or  API_BASE=http://127.0.0.1:8000 ./scripts/test_bot_lifecycle.sh

set -e
API_BASE="${API_BASE:-http://127.0.0.1:8000}"
EMAIL="bot-lifecycle-test-$(date +%s)@gmail.com"
WAIT_START=25
POLL=2
PASS=0
FAIL=0

pass() { echo "  [PASS] $1"; PASS=$((PASS+1)); }
fail() { echo "  [FAIL] $1 — $2"; FAIL=$((FAIL+1)); }

echo "--- Bot Lifecycle E2E ---"
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

echo "4. Token endpoint"
STATUS=$(curl -s -H "Authorization: Bearer $TOKEN" "$API_BASE/user-status/$USER_ID")
echo "$STATUS" | grep -q "tokens_remaining" && pass "user-status has tokens_remaining" || fail "Token endpoint" "missing tokens_remaining"

echo "5. Invalid keys → 400, no auto-start"
HTTP=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_BASE/connect-exchange/by-email" -H "Content-Type: application/json" -d "{\"email\":\"$EMAIL\",\"bfx_key\":\"x\",\"bfx_secret\":\"y\"}")
[ "$HTTP" = "400" ] && pass "Invalid keys return 400" || fail "Invalid keys" "got $HTTP"
BOTSTAT=$(curl -s -H "Authorization: Bearer $TOKEN" "$API_BASE/bot-stats/$USER_ID")
echo "$BOTSTAT" | grep -q '"active":false' && pass "Bot not started after invalid keys" || fail "Invalid keys" "bot should not be active"

echo "6. Manual start"
START=$(curl -s -X POST "$API_BASE/start-bot/$USER_ID" -H "Content-Type: application/json")
echo "$START" | grep -qE "queued|running|success" && pass "Start accepted" || fail "Start" "$START"

echo "7. Poll until active"
ACTIVE="false"
for _ in $(seq 1 $((WAIT_START/POLL))); do
  sleep $POLL
  BOTSTAT=$(curl -s -H "Authorization: Bearer $TOKEN" "$API_BASE/bot-stats/$USER_ID")
  echo "$BOTSTAT" | grep -q '"active":true' && { pass "Bot active"; ACTIVE="true"; break; }
done
[ "$ACTIVE" = "true" ] || fail "Bot active" "timeout (worker running?)"

echo "8. Terminal logs"
LOGS=$(curl -s -H "Authorization: Bearer $TOKEN" "$API_BASE/terminal-logs/$USER_ID")
echo "$LOGS" | grep -q '"lines"' && pass "terminal-logs OK" || fail "Terminal logs" "no lines"

echo "9. Stop bot"
STOP=$(curl -s -X POST "$API_BASE/stop-bot/$USER_ID" -H "Content-Type: application/json")
echo "$STOP" | grep -qE "success|Shutdown" && pass "Stop accepted" || fail "Stop" "$STOP"
sleep 3
BOTSTAT=$(curl -s -H "Authorization: Bearer $TOKEN" "$API_BASE/bot-stats/$USER_ID")
echo "$BOTSTAT" | grep -q '"active":false' && pass "Bot stopped" || fail "Stopped" "still active"

echo "10. Start again"
curl -s -X POST "$API_BASE/start-bot/$USER_ID" -H "Content-Type: application/json" | grep -qE "queued|running|success" && pass "Start again" || fail "Start again" "response"
ACTIVE="false"
for _ in $(seq 1 $((WAIT_START/POLL))); do
  sleep $POLL
  BOTSTAT=$(curl -s -H "Authorization: Bearer $TOKEN" "$API_BASE/bot-stats/$USER_ID")
  echo "$BOTSTAT" | grep -q '"active":true' && { pass "Bot active after 2nd start"; ACTIVE="true"; break; }
done
[ "$ACTIVE" = "true" ] || fail "Bot active 2nd" "timeout"

echo ""
echo "--- Result: $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ]
