# Migration validation: NEW Redis server (Upstash). No references to old account.
# Usage: .\scripts\test_new_redis_migration.ps1

$ErrorActionPreference = "Stop"
$API_BASE = if ($env:API_BASE) { $env:API_BASE } else { "http://127.0.0.1:8000" }
$PASS = 0
$FAIL = 0

function pass($msg) { Write-Host "  [PASS] $msg"; $script:PASS++ }
function fail($msg, $detail) { Write-Host "  [FAIL] $msg — $detail"; $script:FAIL++ }

Set-Location $PSScriptRoot\..

Write-Host "--- NEW Redis migration validation ---"

Write-Host "1. No hardcoded old Upstash host (fancy-kit-48774) in code"
$found = Get-ChildItem -Recurse -Include *.py,*.js -File | Select-String -Pattern "fancy-kit-48774" -List
if ($found) { fail "Old host reference" "Remove fancy-kit-48774 from code" } else { pass "No old Upstash host in code" }

Write-Host "2. REDIS_URL uses rediss://"
if ($env:REDIS_URL -match "rediss://") { pass "REDIS_URL uses rediss:// (SSL)" } else {
  Get-Content .env | ForEach-Object { if ($_ -match "^REDIS_URL=(.+)") { $script:url = $matches[1].Trim('"') } }
  if ($script:url -match "rediss://") { pass "REDIS_URL uses rediss:// (SSL)" } else { fail "REDIS_URL" "Must use rediss:// for Upstash" }
}

Write-Host "3. Redis connectivity (PING)"
$out = python scripts/test_upstash_redis.py 2>&1
if ($out -match "PASS.*ping OK") { pass "Redis connected (ping OK)" } else { fail "Redis" "Run: python scripts/test_upstash_redis.py" }

Write-Host "4. Backend health"
try { Invoke-RestMethod -Uri "$API_BASE/openapi.json" -Method GET -TimeoutSec 3 | Out-Null; pass "Backend reachable" }
catch { fail "Backend" "Start backend and set API_BASE if needed" }

Write-Host "5. Start/Stop bot (200)"
if (-not $env:TEST_JWT) { Write-Host "   (Skipping: set TEST_JWT for full bot test)" }
else {
  $st = (Invoke-WebRequest -Uri "$API_BASE/start-bot" -Method POST -Headers @{ Authorization = "Bearer $env:TEST_JWT" } -UseBasicParsing).StatusCode
  $sp = (Invoke-WebRequest -Uri "$API_BASE/stop-bot" -Method POST -Headers @{ Authorization = "Bearer $env:TEST_JWT" } -UseBasicParsing).StatusCode
  if ($st -eq 200 -and $sp -eq 200) { pass "Start-bot and Stop-bot return 200" } else { fail "Start/Stop bot" "start=$st stop=$sp" }
}

Write-Host ""
Write-Host "--- Result: $PASS passed, $FAIL failed ---"
if ($FAIL -gt 0) { exit 1 }
