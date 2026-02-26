# E2E API test: create test user, login, create-checkout-session (Pro monthly), token deposit ($50).
# No Stripe payment, no DB access. Run from project root. Backend must be running with ALLOW_DEV_CONNECT=1.
# Usage: .\scripts\test_all_features_e2e.ps1

$ErrorActionPreference = "Stop"
$API_BASE = $env:API_BASE
if (-not $API_BASE) { $API_BASE = "http://127.0.0.1:8000" }
$EMAIL = "e2e-test-all@gmail.com"

Write-Host "E2E API test (backend: $API_BASE)" -ForegroundColor Cyan
Write-Host ""

# 1. Create test user
Write-Host "1. Creating test user ($EMAIL)..." -ForegroundColor Yellow
$createBody = '{"email":"e2e-test-all@gmail.com"}'
try {
    $createResp = Invoke-RestMethod -Uri "$API_BASE/dev/create-test-user" -Method POST -ContentType "application/json" -Body $createBody
    $userId = $createResp.user_id
    Write-Host "   user_id=$userId" -ForegroundColor Green
} catch {
    Write-Host "   FAIL: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# 2. Get JWT
Write-Host "2. Getting JWT (login-as)..." -ForegroundColor Yellow
$loginBody = '{"email":"e2e-test-all@gmail.com"}'
try {
    $loginResp = Invoke-RestMethod -Uri "$API_BASE/dev/login-as" -Method POST -ContentType "application/json" -Body $loginBody
    $token = $loginResp.token
    if (-not $token) { throw "No token in response" }
    Write-Host "   OK" -ForegroundColor Green
} catch {
    Write-Host "   FAIL: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

$headers = @{}
$headers["Content-Type"] = "application/json"
$headers["Authorization"] = "Bearer $token"

# 3. Create checkout session (Pro monthly)
Write-Host "3. POST /api/create-checkout-session (plan=pro, interval=monthly)..." -ForegroundColor Yellow
$checkoutBody = '{"plan":"pro","interval":"monthly"}'
try {
    $checkoutResp = Invoke-WebRequest -Uri "$API_BASE/api/create-checkout-session" -Method POST -Headers $headers -Body $checkoutBody -UseBasicParsing
    $status = $checkoutResp.StatusCode
    if ($status -eq 200) {
        Write-Host "   200 OK (Stripe configured)" -ForegroundColor Green
    } elseif ($status -eq 503) {
        Write-Host "   503 (Stripe not configured - acceptable)" -ForegroundColor Green
    } else {
        Write-Host "   Unexpected status: $status" -ForegroundColor Red
        exit 1
    }
} catch {
    $status = $_.Exception.Response.StatusCode.value__
    if ($status -eq 503) {
        Write-Host "   503 (Stripe not configured - acceptable)" -ForegroundColor Green
    } else {
        Write-Host "   FAIL: $($_.Exception.Message)" -ForegroundColor Red
        exit 1
    }
}

# 4. Token deposit $50
Write-Host "4. POST /api/v1/tokens/deposit (usd_amount=50)..." -ForegroundColor Yellow
$depositBody = '{"usd_amount":50}'
try {
    $depositResp = Invoke-RestMethod -Uri "$API_BASE/api/v1/tokens/deposit" -Method POST -Headers $headers -Body $depositBody
    if ($depositResp.status -ne "success") {
        Write-Host "   FAIL: status=$($depositResp.status)" -ForegroundColor Red
        exit 1
    }
    if ($depositResp.tokens_to_award -ne 500) {
        Write-Host "   FAIL: expected tokens_to_award=500, got $($depositResp.tokens_to_award)" -ForegroundColor Red
        exit 1
    }
    Write-Host "   200 OK tokens_to_award=500" -ForegroundColor Green
} catch {
    Write-Host "   FAIL: $($_.Exception.Message)" -ForegroundColor Red
    exit 1
}

# 5. Cleanup instructions
Write-Host ""
Write-Host "5. Cleanup (run in PostgreSQL):" -ForegroundColor Yellow
Write-Host "   DELETE FROM user_token_balance WHERE user_id = $userId;" -ForegroundColor Gray
Write-Host "   DELETE FROM users WHERE id = $userId;" -ForegroundColor Gray
Write-Host ""
Write-Host "All E2E API checks passed." -ForegroundColor Green
