# Run this script as Administrator to free port 8000 and start the backend.
# Right-click PowerShell -> Run as administrator, then:
#   cd c:\Users\choiw\Desktop\bifinex\buildnew\scripts
#   .\restart_backend.ps1

$port = 8000
$conns = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
$pids = $conns.OwningProcess | Sort-Object -Unique
foreach ($p in $pids) {
    if ($p -gt 0) {
        Write-Host "Stopping process $p (was using port $port)..."
        Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
    }
}
Start-Sleep -Seconds 2
Set-Location (Split-Path $PSScriptRoot -Parent)
Write-Host "Starting backend on port $port..."
& python -m uvicorn main:app --host 127.0.0.1 --port $port
