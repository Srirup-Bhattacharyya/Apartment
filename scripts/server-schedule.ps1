param(
    [ValidateSet("Start", "Stop")]
    [string]$Action
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$RuntimeDirectory = Join-Path $ProjectRoot "runtime"
$PidFile = Join-Path $RuntimeDirectory "fastapi.pid"
$LogFile = Join-Path $RuntimeDirectory "fastapi.log"
$ErrorLogFile = Join-Path $RuntimeDirectory "fastapi-error.log"
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (-not (Test-Path -LiteralPath $Python)) {
    $Python = (Get-Command python.exe -ErrorAction Stop).Source
}

New-Item -ItemType Directory -Path $RuntimeDirectory -Force | Out-Null

if ($Action -eq "Stop") {
    if (Test-Path -LiteralPath $PidFile) {
        $processId = [int](Get-Content -LiteralPath $PidFile -Raw).Trim()
        $process = Get-Process -Id $processId -ErrorAction SilentlyContinue
        if ($null -ne $process) {
            Stop-Process -Id $processId -Force
        }
        Remove-Item -LiteralPath $PidFile -Force
    }
    exit 0
}

if (Test-Path -LiteralPath $PidFile) {
    $existingId = [int](Get-Content -LiteralPath $PidFile -Raw).Trim()
    if ($null -ne (Get-Process -Id $existingId -ErrorAction SilentlyContinue)) {
        exit 0
    }
    Remove-Item -LiteralPath $PidFile -Force
}

$process = Start-Process `
    -FilePath $Python `
    -ArgumentList "-m uvicorn backend.main:app --host 0.0.0.0 --port 8000" `
    -WorkingDirectory $ProjectRoot `
    -RedirectStandardOutput $LogFile `
    -RedirectStandardError $ErrorLogFile `
    -PassThru

$process.Id | Set-Content -LiteralPath $PidFile -Encoding ascii
