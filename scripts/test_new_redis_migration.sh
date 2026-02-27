#!/usr/bin/env bash
# Migration validation: NEW Redis server (Upstash). No references to old account.
# Usage: ./scripts/test_new_redis_migration.sh

set -e
cd "$(dirname "$0")/.."
API_BASE="${API_BASE:-http://127.0.0.1:8000}"
PASS=0
FAIL=0

pass() { echo "  [PASS] $1"; PASS=$((PASS+1)); }
fail() { echo "  [FAIL] $1 — $2"; FAIL=$((FAIL+1)); }

echo "--- NEW Redis migration validation ---"

echo "1. No hardcoded old Upstash host (fancy-kit-48774) in code"
if grep -r "fancy-kit-48774" --include="*.py" --include="*.js" . 2>/dev/null | grep -v "^Binary"; then
  fail "Old host reference" "Remove fancy-kit-48774 from code (keep only in .env comment for rollback)"
else
  pass "No old Upstash host in code"
fi

echo "2. REDIS_URL uses rediss://"
if [ -f .env ]; then
  REDIS_URL=$(grep "^REDIS_URL=" .env | head -1 | cut -d= -f2- | tr -d '"')
fi
if echo "$REDIS_URL" | grep -q "rediss://"; then
  pass "REDIS_URL uses rediss:// (SSL)"
else
  fail "REDIS_URL" "Must use rediss:// for Upstash"
fi

echo "3. Redis connectivity (PING)"
if python scripts/test_upstash_redis.py 2>&1 | grep -q "PASS.*ping OK"; then
  pass "Redis connected (ping OK)"
else
  fail "Redis" "Run: python scripts/test_upstash_redis.py"
fi

echo "4. Backend health"
if curl -sf "$API_BASE/openapi.json" -o /dev/null 2>/dev/null; then
  pass "Backend reachable"
else
  fail "Backend" "Start backend and set API_BASE if needed"
fi

echo "5. Start/Stop bot (200)"
TOKEN="${TEST_JWT:-}"
if [ -z "$TOKEN" ]; then
  echo "   (Skipping: set TEST_JWT for full bot test, or run validate_bot_buttons_local.py)"
else
  ST=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_BASE/start-bot" -H "Authorization: Bearer $TOKEN")
  SP=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_BASE/stop-bot" -H "Authorization: Bearer $TOKEN")
  if [ "$ST" = "200" ] && [ "$SP" = "200" ]; then
    pass "Start-bot and Stop-bot return 200"
  else
    fail "Start/Stop bot" "start=$ST stop=$SP"
  fi
fi

echo ""
echo "--- Result: $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ]
