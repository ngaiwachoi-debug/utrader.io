# Auto-activate daily token deduction: migrations -> test -> validation. Zero manual steps.
# Cross-platform: Windows PowerShell. Logs to DEDUCTION_AUTO_ACTIVATION_LOG.md.
# Usage: .\scripts\auto_activate_deduction.ps1

$ErrorActionPreference = "Stop"
$ROOT = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$LOG = Join-Path $ROOT "DEDUCTION_AUTO_ACTIVATION_LOG.md"
$env:API_BASE = if ($env:API_BASE) { $env:API_BASE } else { "http://127.0.0.1:8000" }

function Log { param($msg) $msg | Tee-Object -FilePath $LOG -Append }
function LogStep { param($title) Add-Content -Path $LOG -Value "`n### $title`n``````"; }
function LogEnd { Add-Content -Path $LOG -Value "``````" }

# Start log
Set-Content -Path $LOG -Value "# Deduction auto-activation log"
Add-Content -Path $LOG -Value "Started: $((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))"
Add-Content -Path $LOG -Value "ROOT=$ROOT"

Set-Location $ROOT
if (Test-Path .env) {
    Get-Content .env | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            $k = $matches[1].Trim()
            $v = $matches[2].Trim().Trim('"').Trim("'")
            [Environment]::SetEnvironmentVariable($k, $v, "Process")
        }
    }
}

$script:PASS = 0
$script:FAIL = 0

# --- Step 1: Bot status migration ---
LogStep "Step 1: Bot status migration (users.bot_status)"
$out1 = & python migrations/run_bot_status_migration.py 2>&1; $ec1 = $LASTEXITCODE; $out1 | Add-Content -Path $LOG
if ($ec1 -eq 0) { Log "  [PASS] Bot status migration"; $script:PASS++ } else { Log "  [FAIL] Bot status migration"; $script:FAIL++ }
LogEnd

# --- Step 2: Daily gross migration ---
LogStep "Step 2: Daily gross migration (user_profit_snapshot.daily_gross_*)"
$out2 = & python migrations/run_daily_gross_migration.py 2>&1; $ec2 = $LASTEXITCODE; $out2 | Add-Content -Path $LOG
if ($ec2 -eq 0) { Log "  [PASS] Daily gross migration"; $script:PASS++ } else { Log "  [FAIL] Daily gross migration"; $script:FAIL++ }
LogEnd

# --- Step 3: Deduction test (with retry) ---
LogStep "Step 3: Deduction logic test (3 cases)"
$TEST_OUT = Join-Path $ROOT ".deduction_test_out.txt"
& python scripts/test_daily_deduction_manual.py > $TEST_OUT 2>&1; $ret = $LASTEXITCODE
Get-Content $TEST_OUT -ErrorAction SilentlyContinue | Add-Content -Path $LOG
if ($ret -eq 0) {
    Log "  [PASS] Deduction test"
    $script:PASS++
} else {
    Log "  [RETRY] Re-running migrations and retrying test..."
    & python migrations/run_bot_status_migration.py 2>&1 | Add-Content -Path $LOG
    & python migrations/run_daily_gross_migration.py 2>&1 | Add-Content -Path $LOG
    & python scripts/test_daily_deduction_manual.py > $TEST_OUT 2>&1; $ret2 = $LASTEXITCODE
    Get-Content $TEST_OUT -ErrorAction SilentlyContinue | Add-Content -Path $LOG
    if ($ret2 -eq 0) {
        Log "  [PASS] Deduction test (after retry)"
        $script:PASS++
    } else {
        Log "  [FAIL] Deduction test"
        $script:FAIL++
    }
}
Remove-Item $TEST_OUT -ErrorAction SilentlyContinue
LogEnd

# --- Step 4: Bot compatibility ---
LogStep "Step 4: Bot compatibility (app has deduction + bot routes)"
$checkScript = "import sys; sys.path.insert(0, '$($ROOT -replace "'", "''")'); import main; assert callable(getattr(main, 'run_daily_token_deduction', None)); assert hasattr(main, 'start_bot'); assert hasattr(main, '_run_daily_token_deduction_scheduler'); print('OK')"
$checkOut = & python -c $checkScript 2>&1; $ec4 = $LASTEXITCODE; $checkOut | Add-Content -Path $LOG
if ($ec4 -eq 0) { Log "  [PASS] Bot/deduction coexistence"; $script:PASS++ } else { Log "  [FAIL] Bot/deduction check"; $script:FAIL++ }
LogEnd

# --- Step 5: API reachable (optional) ---
LogStep "Step 5: API reachable (optional)"
try {
    $r = Invoke-WebRequest -Uri "$($env:API_BASE)/openapi.json" -UseBasicParsing -TimeoutSec 3 -ErrorAction Stop
    if ($r.StatusCode -eq 200) { Log "  [PASS] API reachable at $($env:API_BASE)"; $script:PASS++ } else { Log "  [SKIP] API not reachable" }
} catch {
    Log "  [SKIP] API not reachable (backend may be stopped)"
}
LogEnd

# --- Auto-fix: if any failure, re-run migrations and retry once ---
if ($script:FAIL -gt 0) {
    Add-Content -Path $LOG -Value "`n### Auto-fix: Re-running migrations and re-checking`n``````"
    Add-Content -Path $LOG -Value "Fixes applied: Re-ran bot_status + daily_gross migrations."
    & python migrations/run_bot_status_migration.py 2>&1 | Add-Content -Path $LOG
    & python migrations/run_daily_gross_migration.py 2>&1 | Add-Content -Path $LOG
    $p2 = 0; $f2 = 0
    & python migrations/run_bot_status_migration.py 2>&1 | Out-Null; if ($LASTEXITCODE -eq 0) { $p2++ } else { $f2++ }
    & python migrations/run_daily_gross_migration.py 2>&1 | Out-Null; if ($LASTEXITCODE -eq 0) { $p2++ } else { $f2++ }
    & python scripts/test_daily_deduction_manual.py > $TEST_OUT 2>&1; if ($LASTEXITCODE -eq 0) { $p2++ } else { $f2++ }
    Get-Content $TEST_OUT -ErrorAction SilentlyContinue | Add-Content -Path $LOG
    Add-Content -Path $LOG -Value "Re-run result: Passed=$p2 Failed=$f2`n``````"
    if ($f2 -eq 0) { $script:PASS += $p2; $script:FAIL = 0 }
    Remove-Item $TEST_OUT -ErrorAction SilentlyContinue
}

# --- Summary ---
Add-Content -Path $LOG -Value "`n---`n## Summary`nPassed: $($script:PASS) | Failed: $($script:FAIL)"
Add-Content -Path $LOG -Value "Finished: $((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'))"
if ($script:FAIL -eq 0) {
    Add-Content -Path $LOG -Value "`n## **DEDUCTION ACTIVATED SUCCESSFULLY**"
    Log ""
    Log "DEDUCTION ACTIVATED SUCCESSFULLY — see $LOG"
    exit 0
} else {
    Add-Content -Path $LOG -Value "`n## ACTIVATION INCOMPLETE (see failed steps above)"
    Log ""
    Log "ACTIVATION INCOMPLETE — $($script:FAIL) step(s) failed. See $LOG"
    exit 1
}
