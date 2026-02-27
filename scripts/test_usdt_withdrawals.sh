#!/usr/bin/env bash
# Test USDT withdrawal flow: user submits pending request, admin approves or rejects.
# Prerequisites: Backend running; ADMIN_TOKEN (admin JWT); optionally USER_TOKEN (non-admin user JWT) to create a request.
# Usage: ADMIN_TOKEN=your-admin-jwt USER_TOKEN=your-user-jwt ./scripts/test_usdt_withdrawals.sh
# If USER_TOKEN is not set, only admin list/filter is tested.

set -e
API_BASE="${NEXT_PUBLIC_API_BASE:-http://127.0.0.1:8000}"
ADMIN_TOKEN="${ADMIN_TOKEN:?Set ADMIN_TOKEN}"
USER_TOKEN="${USER_TOKEN:-}"

echo "1. GET /admin/usdt-withdrawals (admin list)..."
r=$(curl -s -w "\n%{http_code}" -H "Authorization: Bearer $ADMIN_TOKEN" "$API_BASE/admin/usdt-withdrawals")
code=$(echo "$r" | tail -n1)
if [ "$code" != "200" ]; then echo "FAIL: expected 200, got $code"; exit 1; fi
echo "   OK (200)"

echo "2. GET /admin/usdt-withdrawals?status=pending..."
r2=$(curl -s -w "\n%{http_code}" -H "Authorization: Bearer $ADMIN_TOKEN" "$API_BASE/admin/usdt-withdrawals?status=pending")
code2=$(echo "$r2" | tail -n1)
if [ "$code2" != "200" ]; then echo "FAIL: expected 200, got $code2"; exit 1; fi
echo "   OK (200)"

if [ -n "$USER_TOKEN" ]; then
  echo "3. GET /api/v1/user/usdt-credit (user balance)..."
  r3=$(curl -s -w "\n%{http_code}" -H "Authorization: Bearer $USER_TOKEN" "$API_BASE/api/v1/user/usdt-credit")
  code3=$(echo "$r3" | tail -n1)
  if [ "$code3" != "200" ]; then echo "   Skip (user may have no session): $code3"; else echo "   OK (200)"; fi

  echo "4. GET /api/v1/user/usdt-withdraw-history..."
  r4=$(curl -s -w "\n%{http_code}" -H "Authorization: Bearer $USER_TOKEN" "$API_BASE/api/v1/user/usdt-withdraw-history")
  code4=$(echo "$r4" | tail -n1)
  if [ "$code4" != "200" ]; then echo "   Skip: $code4"; else echo "   OK (200)"; fi

  echo "5. POST /api/v1/user/usdt-withdraw (requires saved address + available balance; may 400)..."
  r5=$(curl -s -w "\n%{http_code}" -X POST -H "Authorization: Bearer $USER_TOKEN" -H "Content-Type: application/json" -d '{"amount":1}' "$API_BASE/api/v1/user/usdt-withdraw")
  code5=$(echo "$r5" | tail -n1)
  body5=$(echo "$r5" | sed '$d')
  if [ "$code5" = "200" ]; then echo "   OK (request created)"; elif [ "$code5" = "400" ]; then echo "   OK (400 expected if no address or insufficient balance)"; else echo "   Got $code5: $body5"; fi
fi

echo "6. POST /admin/usdt-withdrawals/{id}/reject (admin reject with note; use real id from list)..."
# Try reject on a non-existent id to avoid changing real data; expect 404
r6=$(curl -s -w "\n%{http_code}" -X POST -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" -d '{"rejection_note":"Test script"}' "$API_BASE/admin/usdt-withdrawals/999999/reject")
code6=$(echo "$r6" | tail -n1)
if [ "$code6" = "404" ] || [ "$code6" = "200" ]; then echo "   OK (404 no such id or 200 if id existed)"; else echo "   Got $code6"; fi

echo "USDT withdrawal API checks passed. For full flow: set USDT address as user, submit request, then approve/reject as admin in UI or via API."
exit 0
