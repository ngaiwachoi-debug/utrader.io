# Verify Gross Profit backend and DB in one go.
# Run from project root: .\scripts\verify_gross_profit_backend.ps1
#
# PREREQUISITE: Start the backend first in another terminal:
#   cd c:\Users\choiw\Desktop\bifinex\buildnew
#   python -m uvicorn main:app --host 127.0.0.1 --port 8000
# If you see "Cannot reach ... /api/version", the backend is not running on 8000.

$base = "http://127.0.0.1:8000"
$userId = 2

Write-Host "1. Checking /api/version (backend must be from this project)..." -ForegroundColor Cyan
try {
    $ver = Invoke-RestMethod -Uri "$base/api/version" -Method GET
    if ($ver.source_db_supported -eq $true) {
        Write-Host "   OK: Backend has gross-profit-db-fallback support." -ForegroundColor Green
    } else {
        Write-Host "   WARN: Backend responded but source_db_supported is not true. Start backend from project root." -ForegroundColor Yellow
    }
} catch {
    Write-Host "   FAIL: Cannot reach $base/api/version. Start backend: python -m uvicorn main:app --host 127.0.0.1 --port 8000" -ForegroundColor Red
    exit 1
}

Write-Host "2. Checking GET /stats/$userId/lending?source=db (DB snapshot)..." -ForegroundColor Cyan
try {
    $stats = Invoke-RestMethod -Uri "$base/stats/$userId/lending?source=db" -Method GET
    $gross = $stats.gross_profit
    $dbSnap = $stats.db_snapshot_gross
    if ($null -ne $dbSnap) {
        Write-Host "   Backend has new code (db_snapshot_gross in response)." -ForegroundColor Green
    }
    if ($gross -and [double]$gross -gt 0) {
        Write-Host "   OK: gross_profit = $gross (DB has value)." -ForegroundColor Green
    } else {
        Write-Host "   gross_profit = 0. Run seed: python scripts/seed_gross_profit_snapshot.py choiwangai@gmail.com 72.20" -ForegroundColor Yellow
    }
} catch {
    Write-Host "   FAIL: $($_.Exception.Message)" -ForegroundColor Red
}

Write-Host "Done. If both steps are OK, Profit Center should show the gross value." -ForegroundColor Cyan
