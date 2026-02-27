#!/usr/bin/env bash
# Admin panel test script (Bash).
# Prerequisites: Backend running (e.g. http://127.0.0.1:8000), valid admin JWT in env ADMIN_TOKEN.
# Get token: sign in as admin at frontend, then from browser devtools copy the Bearer token from any /admin/* request.
# Usage: export ADMIN_TOKEN="your-jwt"; ./scripts/test_admin_panel.sh

set -e
API_BASE="${NEXT_PUBLIC_API_BASE:-http://127.0.0.1:8000}"
TOKEN="${ADMIN_TOKEN:?Set ADMIN_TOKEN to a valid admin JWT}"

echo "1. GET /admin/users (admin list)..."
code=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $TOKEN" "$API_BASE/admin/users")
if [ "$code" != "200" ]; then echo "FAIL: expected 200, got $code"; exit 1; fi
echo "   OK (200)"

echo "2. GET /admin/users with wrong token (expect 401/403)..."
code=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer wrong-token" "$API_BASE/admin/users")
if [ "$code" = "200" ]; then echo "FAIL: expected 401/403, got 200"; exit 1; fi
echo "   OK ($code)"

echo "3. GET /admin/health..."
code=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $TOKEN" "$API_BASE/admin/health")
if [ "$code" != "200" ]; then echo "FAIL: expected 200, got $code"; exit 1; fi
echo "   OK (200)"

echo "4. GET /admin/deduction/logs..."
code=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $TOKEN" "$API_BASE/admin/deduction/logs?limit=10")
if [ "$code" != "200" ]; then echo "FAIL: expected 200, got $code"; exit 1; fi
echo "   OK (200)"

echo "5. GET /admin/audit-logs..."
code=$(curl -s -o /dev/null -w "%{http_code}" -H "Authorization: Bearer $TOKEN" "$API_BASE/admin/audit-logs?limit=10")
if [ "$code" != "200" ]; then echo "FAIL: expected 200, got $code"; exit 1; fi
echo "   OK (200)"

echo "6. GET /admin/users/export (CSV)..."
code=$(curl -s -o /tmp/admin_export.csv -w "%{http_code}" -H "Authorization: Bearer $TOKEN" "$API_BASE/admin/users/export")
if [ "$code" != "200" ]; then echo "FAIL: expected 200, got $code"; exit 1; fi
if ! grep -q "id,email," /tmp/admin_export.csv; then echo "FAIL: CSV header not found"; exit 1; fi
echo "   OK (200, CSV)"

echo "All admin panel API checks passed. For full E2E (login as admin -> redirect, edit user, bot, deduction), run manually in browser."
