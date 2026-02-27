# Register uTrader backend as a Windows Service (auto-start on boot).
# Loads .env from project root; no hardcoded credentials.
# Requires: Run as Administrator for New-Service / NSSM.
#
# Option A - Using NSSM (recommended): download nssm.exe, then:
#   nssm install UtraderAPI "C:\Python311\python.exe" "-m uvicorn main:app --host 0.0.0.0 --port 8000"
#   nssm set UtraderAPI AppDirectory "C:\path\to\buildnew"
#   nssm set UtraderAPI AppEnvironmentExtra "DATABASE_URL=..." (or use .env in AppDirectory)
#   nssm start UtraderAPI
#
# Option B - Using PowerShell (creates a service that runs a wrapper script):
#   .\scripts\utrader-service.ps1 -Register
#   .\scripts\utrader-service.ps1 -Unregister

param(
    [ValidateSet("Register", "Unregister", "Status")]
    [string]$Action = "Status"
)

$ServiceName = "UtraderAPI"
$ROOT = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Python = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $Python) { $Python = (Get-Command py -ErrorAction SilentlyContinue).Source }
if (-not $Python) { Write-Error "python not found in PATH"; exit 1 }

$UvicornArgs = "-m uvicorn main:app --host 0.0.0.0 --port 8000"
$WrapperScript = Join-Path $ROOT "scripts\utrader-service-wrapper.ps1"

function EnsureWrapper {
    $content = @"
Set-Location '$ROOT'
if (Test-Path '$ROOT\.env') {
    Get-Content '$ROOT\.env' | ForEach-Object {
        if (`$_ -match '^\s*([^#][^=]+)=(.*)$') {
            [Environment]::SetEnvironmentVariable(`$matches[1].Trim(), `$matches[2].Trim().Trim('"').Trim("'"), 'Process')
        }
    }
}
& '$Python' -m uvicorn main:app --host 0.0.0.0 --port 8000
"@
    Set-Content -Path $WrapperScript -Value $content -Encoding UTF8
}

switch ($Action) {
    "Register" {
        EnsureWrapper
        $bin = (Get-Command pwsh -ErrorAction SilentlyContinue).Source
        if (-not $bin) { $bin = "powershell.exe" }
        New-Service -Name $ServiceName -BinaryPathName "`"$bin`" -NoProfile -ExecutionPolicy Bypass -File `"$WrapperScript`"" -DisplayName "uTrader API" -StartupType Automatic -ErrorAction Stop
        Write-Host "Service $ServiceName registered. Start with: Start-Service $ServiceName"
    }
    "Unregister" {
        Stop-Service $ServiceName -ErrorAction SilentlyContinue
        sc.exe delete $ServiceName
        Write-Host "Service $ServiceName removed."
    }
    "Status" {
        Get-Service $ServiceName -ErrorAction SilentlyContinue
        if (-not $?) { Write-Host "Service $ServiceName not installed. Use -Register to install." }
    }
}
