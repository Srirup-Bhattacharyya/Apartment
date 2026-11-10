$ErrorActionPreference = "Stop"

New-NetFirewallRule `
    -DisplayName "Shraddhanjalli FastAPI (TCP 8000)" `
    -Direction Inbound `
    -Action Allow `
    -Protocol TCP `
    -LocalPort 8000 `
    -Profile Private `
    -ErrorAction SilentlyContinue | Out-Null

Write-Output "Windows Firewall access enabled for TCP port 8000 on Private networks."
