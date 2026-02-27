# Validation for fixed Start/Stop Bot buttons. Requires ALLOW_DEV_CONNECT=1 and ARQ worker.
# Usage: .\scripts\test_bot_buttons.ps1

$ErrorActionPreference = "Stop"
$API_BASE = if ($env:API_BASE) { $env:API_BASE } else { "http://127.0.0.1:8000" }
$EMAIL = "bot-buttons-test-$(Get-Date -UFormat %s)@gmail.com"
$WAIT_START = 30
$POLL = 2
$PASS = 0
$FAIL = 0

function pass($msg) { Write-Host "  [PASS] $msg"; $script:PASS++ }
function fail($msg, $detail) { Write-Host "  [FAIL] $msg — $detail"; $script:FAIL++ }

Write-Host "--- Bot Buttons Validation ---"
Write-Host "API_BASE=$API_BASE  EMAIL=$EMAIL"

Write-Host "1. Backend health"
try { Invoke-RestMethod -Uri "$API_BASE/openapi.json" -Method GET | Out-Null; pass "Backend reachable" }
catch { fail "Backend" "unreachable"; exit 1 }

Write-Host "2. Create test user"
$create = Invoke-RestMethod -Uri "$API_BASE/dev/create-test-user" -Method POST -ContentType "application/json" -Body (@{ email = $EMAIL } | ConvertTo-Json)
$USER_ID = $create.user_id
if (-not $USER_ID) { fail "Create user" ($create | ConvertTo-Json); exit 1 }
pass "Create test user (user_id=$USER_ID)"

Write-Host "3. Get JWT"
$login = Invoke-RestMethod -Uri "$API_BASE/dev/login-as" -Method POST -ContentType "application/json" -Body (@{ email = $EMAIL } | ConvertTo-Json)
$TOKEN = $login.token
if (-not $TOKEN) { fail "JWT" ($login | ConvertTo-Json); exit 1 }
pass "Get JWT"

$headers = @{ "Authorization" = "Bearer $TOKEN"; "Content-Type" = "application/json" }

Write-Host "5. Start Bot"
$start1 = Invoke-RestMethod -Uri "$API_BASE/start-bot" -Method POST -Headers $headers
if ($start1.status -eq "success") { pass "Start Bot success" } else { fail "Start Bot" ($start1 | ConvertTo-Json) }

Write-Host "6. Poll until active"
$active = $false
for ($i = 0; $i -lt ($WAIT_START / $POLL); $i++) {
  Start-Sleep -Seconds $POLL
  $botstat = Invoke-RestMethod -Uri "$API_BASE/bot-stats/$USER_ID" -Headers @{ "Authorization" = "Bearer $TOKEN" }
  if ($botstat.active -eq $true) { pass "Bot active"; $active = $true; break }
}
if (-not $active) { fail "Bot active" "timeout" }

Write-Host "7. Stop Bot"
$stop = Invoke-RestMethod -Uri "$API_BASE/stop-bot" -Method POST -Headers $headers
if ($stop.status -eq "success") { pass "Stop Bot success" } else { fail "Stop Bot" ($stop | ConvertTo-Json) }
Start-Sleep -Seconds 3
$botstat = Invoke-RestMethod -Uri "$API_BASE/bot-stats/$USER_ID" -Headers @{ "Authorization" = "Bearer $TOKEN" }
if ($botstat.active -eq $false) { pass "Bot stopped" } else { fail "Stopped" "still active" }

Write-Host "8. Start again"
$start2 = Invoke-RestMethod -Uri "$API_BASE/start-bot" -Method POST -Headers $headers
if ($start2.status -eq "success") { pass "Start again success" } else { fail "Start again" ($start2 | ConvertTo-Json) }

Write-Host "9. Duplicate Start (idempotent)"
$start3 = Invoke-RestMethod -Uri "$API_BASE/start-bot" -Method POST -Headers $headers
if ($start3.status -eq "success") { pass "Duplicate Start success" } else { fail "Duplicate Start" ($start3 | ConvertTo-Json) }

Write-Host "10. Terminal logs"
$logs = Invoke-RestMethod -Uri "$API_BASE/terminal-logs/$USER_ID" -Headers @{ "Authorization" = "Bearer $TOKEN" }
if ($logs.lines -ne $null) { pass "terminal-logs OK" } else { fail "Terminal logs" "no lines" }

Write-Host ""
Write-Host "--- Result: $PASS passed, $FAIL failed ---"
if ($FAIL -gt 0) { exit 1 }
