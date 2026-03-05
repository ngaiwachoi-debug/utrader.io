# Restart all function servers: backend (uvicorn), ARQ worker, frontend (Next.js), Stripe CLI webhook.
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

# 4) Stop existing Stripe CLI listen (if running)
Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like '*stripe*' -and $_.CommandLine -like '*listen*' } | ForEach-Object {
    Write-Host "Stopping Stripe listen (PID $($_.ProcessId))..."
    Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue
}

Remove-Item "$root\frontend\.next\dev\lock" -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# 5) Start backend, worker, frontend, and Stripe webhook in this terminal (Cursor) as background jobs
Write-Host "Starting backend, worker, frontend, and Stripe webhook..."
$jobBackend  = Start-Job -ScriptBlock { param($r) Set-Location $r; python -m uvicorn main:app --host 127.0.0.1 --port 8000 } -ArgumentList $root
$jobWorker   = Start-Job -ScriptBlock { param($r) Set-Location $r; python scripts/run_worker.py } -ArgumentList $root
$jobFrontend = Start-Job -ScriptBlock { param($r) Set-Location (Join-Path $r "frontend"); npm run dev } -ArgumentList $root
$jobStripe   = Start-Job -ScriptBlock { stripe listen --forward-to http://127.0.0.1:8000/webhook/stripe }

Write-Host "Backend: http://127.0.0.1:8000  |  Frontend: http://localhost:3000  |  Stripe: forwarding to /webhook/stripe"
Write-Host "Streaming output (Ctrl+C to stop script; jobs may keep running).`n"
try {
    Receive-Job -Wait -Id $jobBackend.Id, $jobWorker.Id, $jobFrontend.Id, $jobStripe.Id
} finally {
    Get-Job | Where-Object { $_.Id -in @($jobBackend.Id, $jobWorker.Id, $jobFrontend.Id, $jobStripe.Id) } | Stop-Job -ErrorAction SilentlyContinue
    Get-Job | Where-Object { $_.Id -in @($jobBackend.Id, $jobWorker.Id, $jobFrontend.Id, $jobStripe.Id) } | Remove-Job -Force -ErrorAction SilentlyContinue
}
