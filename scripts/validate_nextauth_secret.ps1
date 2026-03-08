# Validate/sync NEXTAUTH_SECRET between root .env and frontend/.env.local
# Run from project root: powershell -ExecutionPolicy Bypass -File scripts/validate_nextauth_secret.ps1

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot + "\.."
$rootEnv = Join-Path $root ".env"
$frontendEnv = Join-Path $root "frontend\.env.local"

# 1) Check root .env and extract the secret (never hardcode it)
if (-not (Test-Path $rootEnv)) {
    Write-Host "ERROR: Root .env not found at $rootEnv"
    exit 1
}
$rootContent = Get-Content $rootEnv -Raw
if ($rootContent -match 'NEXTAUTH_SECRET\s*=\s*"([^"]+)"') {
    $exactSecret = $Matches[1]
    Write-Host "OK: Root .env contains NEXTAUTH_SECRET"
} elseif ($rootContent -match 'NEXTAUTH_SECRET\s*=\s*(\S+)') {
    $exactSecret = $Matches[1]
    Write-Host "OK: Root .env contains NEXTAUTH_SECRET (unquoted)"
} else {
    Write-Host "ERROR: Root .env has no NEXTAUTH_SECRET=... line. Generate one with: node -e `"console.log(require('crypto').randomBytes(32).toString('base64'))`""
    exit 1
}
$line = "NEXTAUTH_SECRET=`"$exactSecret`""

# 2) Create or overwrite frontend/.env.local with same secret (UTF-8 no BOM so Next.js reads it correctly)
$frontendDir = Join-Path $root "frontend"
if (-not (Test-Path $frontendDir)) {
    Write-Host "ERROR: frontend folder not found"
    exit 1
}
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($frontendEnv, $line + "`n", $utf8NoBom)
Write-Host "OK: frontend/.env.local written with NEXTAUTH_SECRET (same as root, no BOM)"
Write-Host "Next: Restart backend and frontend, then re-login and test /api-backend/user-status/2"
exit 0
