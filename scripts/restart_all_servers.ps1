# Restart all function servers: backend (uvicorn), ARQ worker, frontend (Next.js).
# For port 8000 to be freed, run PowerShell as Administrator, then:
#   cd c:\Users\choiw\Desktop\bifinex\buildnew\scripts
#   .\restart_all_servers.ps1

$root = Split-Path $PSScriptRoot -Parent

# 1) Stop Node (frontend)
Write-Host "Stopping Node (frontend)..."
taskkill /F /IM node.exe 2>$null

# 2) Free port 8000 (backend)
$port = 8000
$conns = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue
$pids = $conns.OwningProcess | Sort-Object -Unique
foreach ($p in $pids) {
    if ($p -gt 0) {
        Write-Host "Stopping process $p (was using port $port)..."
        Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
    }
}

# 3) Stop ARQ worker (python processes running arq worker)
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*arq*' -and $_.CommandLine -like '*worker*' } | ForEach-Object {
    Write-Host "Stopping ARQ worker (PID $($_.ProcessId))..."
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

Remove-Item "$root\frontend\.next\dev\lock" -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# 4) Start backend (foreground in this window - or use Start-Process to open new windows)
Write-Host "Starting backend on port $port..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root'; python -m uvicorn main:app --host 127.0.0.1 --port $port"

Start-Sleep -Seconds 3

# 5) Start worker in new window
Write-Host "Starting ARQ worker..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root'; python scripts/run_worker.py"

Start-Sleep -Seconds 2

# 6) Start frontend in new window
Write-Host "Starting frontend..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$root\frontend'; npm run dev"

Write-Host "`nDone. Backend, worker, and frontend started in separate windows."
Write-Host "Backend: http://127.0.0.1:8000  |  Frontend: http://localhost:3000"
