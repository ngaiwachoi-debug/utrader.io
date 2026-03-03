# Bot lifecycle E2E: register user, add keys (optional), manual start, stop, start, verify logs and token endpoint.
# Requires: backend running with ALLOW_DEV_CONNECT=1; ARQ worker running for bot logs.
#
# Usage: .\scripts\test_bot_lifecycle.ps1
#   or:  $env:API_BASE = "http://127.0.0.1:8000"; .\scripts\test_bot_lifecycle.ps1

$ErrorActionPreference = "Stop"
$API_BASE = if ($env:API_BASE) { $env:API_BASE } else { "http://127.0.0.1:8000" }
$EMAIL = "bot-lifecycle-test-$(Get-Date -Format 'yyyyMMddHHmmss')@gmail.com"
$WAIT_START = 25
$POLL = 2
$script:PASS = 0
$script:FAIL = 0

function pass { param($msg) Write-Host "  [PASS] $msg" -ForegroundColor Green; $script:PASS++ }
function fail { param($msg, $detail) Write-Host "  [FAIL] $msg — $detail" -ForegroundColor Red; $script:FAIL++ }

Write-Host "--- Bot Lifecycle E2E ---"
Write-Host "API_BASE=$API_BASE  EMAIL=$EMAIL"
Write-Host ""

# 1) Backend health
Write-Host "1. Backend health"
try {
    $r = Invoke-WebRequest -Uri "$API_BASE/openapi.json" -UseBasicParsing -TimeoutSec 5
    if ($r.StatusCode -eq 200) { pass "Backend reachable" } else { fail "Backend health" "Status $($r.StatusCode)" }
} catch {
    fail "Backend health" $_.Exception.Message
    exit 1
}

# 2) Create test user
Write-Host "2. Create test user"
try {
    $body = @{ email = $EMAIL } | ConvertTo-Json
    $r = Invoke-RestMethod -Uri "$API_BASE/dev/create-test-user" -Method POST -Body $body -ContentType "application/json"
    $USER_ID = $r.user_id
    if (-not $USER_ID) { fail "Create test user" "No user_id"; exit 1 }
    pass "Create test user (user_id=$USER_ID)"
} catch {
    fail "Create test user" $_.Exception.Message
    exit 1
}

# 3) Get JWT
Write-Host "3. Get JWT (dev login-as)"
try {
    $body = @{ email = $EMAIL } | ConvertTo-Json
    $r = Invoke-RestMethod -Uri "$API_BASE/dev/login-as" -Method POST -Body $body -ContentType "application/json"
    $TOKEN = $r.token
    if (-not $TOKEN) { fail "Get JWT" "No token"; exit 1 }
    pass "Get JWT"
} catch {
    fail "Get JWT" $_.Exception.Message
    exit 1
}

$headers = @{ Authorization = "Bearer $TOKEN" }

# 4) Token endpoint
Write-Host "4. Token / user-status endpoint"
try {
    $r = Invoke-RestMethod -Uri "$API_BASE/user-status/$USER_ID" -Headers $headers
    if ($null -ne $r.tokens_remaining) { pass "user-status returns tokens_remaining=$($r.tokens_remaining)" }
    else { fail "Token endpoint" "user-status missing tokens_remaining" }
} catch {
    fail "Token endpoint" $_.Exception.Message
}

# 5) Invalid API keys → 400
Write-Host "5. Invalid API keys → 400, no auto-start"
try {
    $body = @{ email = $EMAIL; bfx_key = "invalid"; bfx_secret = "invalid" } | ConvertTo-Json
    Invoke-RestMethod -Uri "$API_BASE/connect-exchange/by-email" -Method POST -Body $body -ContentType "application/json" -ErrorAction Stop
    fail "Invalid keys" "expected 400"
} catch {
    if ($_.Exception.Response.StatusCode.value__ -eq 400) { pass "Invalid keys return 400" }
    else { fail "Invalid keys" $_.Exception.Message }
}
try {
    $botStat = Invoke-RestMethod -Uri "$API_BASE/bot-stats/$USER_ID" -Headers $headers
    if ($botStat.active -eq $false) { pass "Bot not started after invalid keys" }
    else { fail "Invalid keys" "bot should not be active" }
} catch {
    fail "bot-stats after invalid keys" $_.Exception.Message
}

# 6) Manual start (with user JWT)
Write-Host "6. Manual start bot"
try {
    $r = Invoke-RestMethod -Uri "$API_BASE/start-bot/$USER_ID" -Method POST -Headers $headers -ContentType "application/json"
    if ($r.message -match "queued|running|success") { pass "Start bot accepted" }
    else { fail "Start bot" $r.message }
} catch {
    fail "Start bot" $_.Exception.Message
}

# 7) Poll until active
Write-Host "7. Poll bot-stats until active (up to ${WAIT_START}s)"
$active = $false
for ($i = 0; $i -lt ($WAIT_START / $POLL); $i++) {
    Start-Sleep -Seconds $POLL
    try {
        $botStat = Invoke-RestMethod -Uri "$API_BASE/bot-stats/$USER_ID" -Headers $headers
        if ($botStat.active -eq $true) { pass "Bot active after start"; $active = $true; break }
    } catch {}
}
if (-not $active) { fail "Bot active" "still inactive after ${WAIT_START}s (is worker running?)" }

# 8) Terminal logs
Write-Host "8. Terminal logs"
try {
    $logs = Invoke-RestMethod -Uri "$API_BASE/terminal-logs/$USER_ID" -Headers $headers
    if ($logs.lines -is [Array] -and $logs.lines.Count -ge 0) { pass "terminal-logs returns lines" }
    else { fail "Terminal logs" "no lines" }
} catch {
    fail "Terminal logs" $_.Exception.Message
}

# 9) Stop bot (with user JWT)
Write-Host "9. Stop bot"
try {
    $r = Invoke-RestMethod -Uri "$API_BASE/stop-bot/$USER_ID" -Method POST -Headers $headers -ContentType "application/json"
    if ($r.message -match "success|Shutdown") { pass "Stop bot accepted" }
    else { fail "Stop bot" $r.message }
} catch {
    fail "Stop bot" $_.Exception.Message
}
Start-Sleep -Seconds 3
try {
    $botStat = Invoke-RestMethod -Uri "$API_BASE/bot-stats/$USER_ID" -Headers $headers
    if ($botStat.active -eq $false) { pass "Bot stopped" }
    else { fail "Bot stopped" "still active" }
} catch {
    fail "Bot stopped" $_.Exception.Message
}

# 10) Start again (with user JWT)
Write-Host "10. Start bot again"
try {
    $r = Invoke-RestMethod -Uri "$API_BASE/start-bot/$USER_ID" -Method POST -Headers $headers -ContentType "application/json"
    if ($r.message -match "queued|running|success") { pass "Start again accepted" }
    else { fail "Start again" $r.message }
} catch {
    fail "Start again" $_.Exception.Message
}
$active = $false
for ($i = 0; $i -lt ($WAIT_START / $POLL); $i++) {
    Start-Sleep -Seconds $POLL
    try {
        $botStat = Invoke-RestMethod -Uri "$API_BASE/bot-stats/$USER_ID" -Headers $headers
        if ($botStat.active -eq $true) { pass "Bot active after second start"; $active = $true; break }
    } catch {}
}
if (-not $active) { fail "Bot active after second start" "still inactive" }

Write-Host ""
Write-Host "--- Result: $($script:PASS) passed, $($script:FAIL) failed ---"
if ($script:FAIL -gt 0) { exit 1 }
