# Watchdog: ensure uTrader backend (and thus 09:40/10:15 schedulers) is running. Restart if down.
# Run via Task Scheduler every 1-5 min, or in a loop. Uses existing .env; no hardcoded credentials.
# Usage: .\scripts\deduction_watchdog.ps1

$ROOT = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
Set-Location $ROOT
if (Test-Path .env) {
    Get-Content .env | ForEach-Object {
        if ($_ -match '^\s*([^#][^=]+)=(.*)$') {
            [Environment]::SetEnvironmentVariable($matches[1].Trim(), $matches[2].Trim().Trim('"').Trim("'"), "Process")
        }
    }
}
$API_BASE = if ($env:API_BASE) { $env:API_BASE } else { "http://127.0.0.1:8000" }
$logDir = Join-Path $ROOT "logs"
if (-not (Test-Path $logDir)) { New-Item -ItemType Directory -Path $logDir -Force | Out-Null }
$LOG = Join-Path $logDir "deduction_watchdog.log"

try {
    $r = Invoke-WebRequest -Uri "$API_BASE/openapi.json" -UseBasicParsing -TimeoutSec 5 -ErrorAction Stop
    if ($r.StatusCode -eq 200) { exit 0 }
} catch {}

Add-Content -Path $LOG -Value "$((Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')) backend not reachable, starting uvicorn"
$python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $python) { $python = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $python) { Add-Content -Path $LOG -Value "python not found"; exit 1 }
Start-Process -FilePath $python -ArgumentList "-m uvicorn main:app --host 0.0.0.0 --port 8000" -WorkingDirectory $ROOT -WindowStyle Hidden -RedirectStandardOutput (Join-Path $logDir "uvicorn.out.log") -RedirectStandardError (Join-Path $logDir "uvicorn.err.log")
