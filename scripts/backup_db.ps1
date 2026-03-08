<#
.SYNOPSIS
    Database backup script for uTrader/bifinexbot.
    Creates a timestamped pg_dump and rotates old backups.

.USAGE
    # One-time:
    powershell -ExecutionPolicy Bypass -File scripts\backup_db.ps1

    # Schedule daily (Windows Task Scheduler):
    schtasks /create /tn "uTrader DB Backup" /tr "powershell -ExecutionPolicy Bypass -File C:\path\to\scripts\backup_db.ps1" /sc daily /st 04:00
#>

$ErrorActionPreference = "Stop"
$root = Split-Path $PSScriptRoot
$envFile = Join-Path $root ".env"

# Load DATABASE_URL from .env
if (-not (Test-Path $envFile)) {
    Write-Host "ERROR: .env not found at $envFile"
    exit 1
}
$dbUrl = ""
Get-Content $envFile | ForEach-Object {
    if ($_ -match '^\s*DATABASE_URL\s*=\s*"?([^"]+)"?') {
        $dbUrl = $Matches[1]
    }
}
if (-not $dbUrl) {
    Write-Host "ERROR: DATABASE_URL not found in .env"
    exit 1
}

# Backup directory
$backupDir = Join-Path $root "backups"
if (-not (Test-Path $backupDir)) {
    New-Item -ItemType Directory -Path $backupDir -Force | Out-Null
}

$timestamp = Get-Date -Format "yyyy-MM-dd_HHmmss"
$backupFile = Join-Path $backupDir "utrader_$timestamp.sql.gz"

Write-Host "Starting database backup..."
Write-Host "  Target: $backupFile"

# pg_dump via DATABASE_URL (works with Neon, Supabase, local PG, etc.)
try {
    $env:PGPASSWORD = ""
    pg_dump $dbUrl --no-owner --no-acl | gzip > $backupFile
    $size = (Get-Item $backupFile).Length
    Write-Host "OK: Backup complete ($([math]::Round($size/1KB, 1)) KB)"
} catch {
    Write-Host "ERROR: pg_dump failed. Ensure pg_dump is in PATH."
    Write-Host "  Install: https://www.postgresql.org/download/"
    Write-Host "  Error: $($_.Exception.Message)"
    exit 1
}

# Rotate: keep last 30 backups
$backups = Get-ChildItem $backupDir -Filter "utrader_*.sql.gz" | Sort-Object LastWriteTime -Descending
$keep = 30
if ($backups.Count -gt $keep) {
    $toRemove = $backups[$keep..($backups.Count - 1)]
    $toRemove | ForEach-Object {
        Remove-Item $_.FullName -Force
        Write-Host "  Rotated: $($_.Name)"
    }
}

Write-Host "Done. $($backups.Count) backups in $backupDir (keeping last $keep)."
