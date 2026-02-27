# Admin panel test script (PowerShell).
# Prerequisites: Backend running (e.g. http://127.0.0.1:8000), valid admin JWT in env ADMIN_TOKEN.
# Get token: sign in as admin at frontend, then from browser devtools copy the Bearer token from any /admin/* request,
# or use the NextAuth session to call /api/auth/token and use the returned token.
# Usage: $env:ADMIN_TOKEN = "your-jwt"; .\scripts\test_admin_panel.ps1

$ErrorActionPreference = "Stop"
$API_BASE = if ($env:NEXT_PUBLIC_API_BASE) { $env:NEXT_PUBLIC_API_BASE } else { "http://127.0.0.1:8000" }
$TOKEN = $env:ADMIN_TOKEN
if (-not $TOKEN) {
    Write-Host "Set ADMIN_TOKEN to a valid admin JWT. Example: `$env:ADMIN_TOKEN = 'eyJ...'"
    exit 1
}

$headers = @{
    "Authorization" = "Bearer $TOKEN"
    "Content-Type"  = "application/json"
}

Write-Host "1. GET /admin/users (admin list)..."
$r = Invoke-WebRequest -Uri "$API_BASE/admin/users" -Headers @{ "Authorization" = "Bearer $TOKEN" } -UseBasicParsing
if ($r.StatusCode -ne 200) { Write-Host "FAIL: expected 200, got $($r.StatusCode)"; exit 1 }
Write-Host "   OK (200)"

Write-Host "2. GET /admin/users with wrong token (expect 403)..."
try {
    $r2 = Invoke-WebRequest -Uri "$API_BASE/admin/users" -Headers @{ "Authorization" = "Bearer wrong-token" } -UseBasicParsing
    Write-Host "   FAIL: expected 403, got $($r2.StatusCode)"
    exit 1
} catch {
    if ($_.Exception.Response.StatusCode.value__ -eq 401) { Write-Host "   OK (401 Unauthorized)" }
    elseif ($_.Exception.Response.StatusCode.value__ -eq 403) { Write-Host "   OK (403 Forbidden)" }
    else { Write-Host "   OK (non-200)" }
}

Write-Host "3. GET /admin/health..."
$r3 = Invoke-WebRequest -Uri "$API_BASE/admin/health" -Headers $headers -UseBasicParsing
if ($r3.StatusCode -ne 200) { Write-Host "FAIL: expected 200, got $($r3.StatusCode)"; exit 1 }
$health = $r3.Content | ConvertFrom-Json
Write-Host "   Redis: $($health.redis), DB: $($health.db)"

Write-Host "4. GET /admin/deduction/logs..."
$r4 = Invoke-WebRequest -Uri "$API_BASE/admin/deduction/logs?limit=10" -Headers $headers -UseBasicParsing
if ($r4.StatusCode -ne 200) { Write-Host "FAIL: expected 200, got $($r4.StatusCode)"; exit 1 }
Write-Host "   OK (200)"

Write-Host "5. GET /admin/audit-logs..."
$r5 = Invoke-WebRequest -Uri "$API_BASE/admin/audit-logs?limit=10" -Headers $headers -UseBasicParsing
if ($r5.StatusCode -ne 200) { Write-Host "FAIL: expected 200, got $($r5.StatusCode)"; exit 1 }
Write-Host "   OK (200)"

Write-Host "6. GET /admin/users/export (CSV)..."
$r6 = Invoke-WebRequest -Uri "$API_BASE/admin/users/export" -Headers $headers -UseBasicParsing
if ($r6.StatusCode -ne 200) { Write-Host "FAIL: expected 200, got $($r6.StatusCode)"; exit 1 }
if (-not ($r6.Content -match "id,email,")) { Write-Host "FAIL: CSV header not found"; exit 1 }
Write-Host "   OK (200, CSV)"

Write-Host "All admin panel API checks passed. For full E2E (login as admin -> redirect, edit user, bot, deduction), run manually in browser."
exit 0
