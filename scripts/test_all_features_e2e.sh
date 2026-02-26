#!/usr/bin/env bash
# E2E API test: create test user, login, create-checkout-session (Pro monthly), token deposit ($50).
# No Stripe payment, no DB access. Run from project root. Backend must be running with ALLOW_DEV_CONNECT=1.
# Usage: ./scripts/test_all_features_e2e.sh

set -e
API_BASE="${API_BASE:-http://127.0.0.1:8000}"
EMAIL="e2e-test-all@gmail.com"

echo "E2E API test (backend: $API_BASE)"
echo ""

# 1. Create test user
echo "1. Creating test user ($EMAIL)..."
CREATE_RESP=$(curl -s -X POST "$API_BASE/dev/create-test-user" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\"}")
USER_ID=$(echo "$CREATE_RESP" | grep -o '"user_id":[0-9]*' | cut -d: -f2)
if [ -z "$USER_ID" ]; then
  echo "   FAIL: $CREATE_RESP"
  exit 1
fi
echo "   user_id=$USER_ID"

# 2. Get JWT
echo "2. Getting JWT (login-as)..."
LOGIN_RESP=$(curl -s -X POST "$API_BASE/dev/login-as" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\"}")
TOKEN=$(echo "$LOGIN_RESP" | grep -o '"token":"[^"]*"' | cut -d'"' -f4)
if [ -z "$TOKEN" ]; then
  echo "   FAIL: $LOGIN_RESP"
  exit 1
fi
echo "   OK"

# 3. Create checkout session (Pro monthly)
echo "3. POST /api/create-checkout-session (plan=pro, interval=monthly)..."
CHECKOUT_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$API_BASE/api/create-checkout-session" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"plan":"pro","interval":"monthly"}')
if [ "$CHECKOUT_STATUS" = "200" ]; then
  echo "   200 OK (Stripe configured)"
elif [ "$CHECKOUT_STATUS" = "503" ]; then
  echo "   503 (Stripe not configured - acceptable)"
else
  echo "   FAIL: unexpected status $CHECKOUT_STATUS"
  exit 1
fi

# 4. Token deposit $50
echo "4. POST /api/v1/tokens/deposit (usd_amount=50)..."
DEPOSIT_RESP=$(curl -s -X POST "$API_BASE/api/v1/tokens/deposit" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"usd_amount":50}')
STATUS=$(echo "$DEPOSIT_RESP" | grep -o '"status":"[^"]*"' | cut -d'"' -f4)
TOKENS=$(echo "$DEPOSIT_RESP" | grep -o '"tokens_to_award":[0-9]*' | cut -d: -f2)
if [ "$STATUS" != "success" ]; then
  echo "   FAIL: $DEPOSIT_RESP"
  exit 1
fi
if [ "$TOKENS" != "500" ]; then
  echo "   FAIL: expected tokens_to_award=500, got $TOKENS"
  exit 1
fi
echo "   200 OK tokens_to_award=500"

# 5. Cleanup instructions
echo ""
echo "5. Cleanup (run in PostgreSQL):"
echo "   DELETE FROM user_token_balance WHERE user_id = $USER_ID;"
echo "   DELETE FROM users WHERE id = $USER_ID;"
echo ""
echo "All E2E API checks passed."
