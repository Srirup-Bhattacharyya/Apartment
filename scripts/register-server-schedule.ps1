$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
$Runner = Join-Path $ProjectRoot "scripts\server-schedule.ps1"
$PowerShell = (Get-Command powershell.exe).Source

$tasks = @(
    @{ Name = "Shraddhanjalli Server Start Morning"; Time = "09:00"; Action = "Start" },
    @{ Name = "Shraddhanjalli Server Stop Evening"; Time = "16:00"; Action = "Stop" },
    @{ Name = "Shraddhanjalli Server Start Evening"; Time = "18:30"; Action = "Start" },
    @{ Name = "Shraddhanjalli Server Stop Morning"; Time = "03:30"; Action = "Stop" }
)

foreach ($task in $tasks) {
    $action = New-ScheduledTaskAction `
        -Execute $PowerShell `
        -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$Runner`" -Action $($task.Action)"
    $trigger = New-ScheduledTaskTrigger -Daily -At $task.Time
    Register-ScheduledTask `
        -TaskName $task.Name `
        -Action $action `
        -Trigger $trigger `
        -Description "Shraddhanjalli Apartment server schedule" `
        -Force | Out-Null
}

Write-Output "Schedule registered: 09:00-16:00 and 18:30-03:30."
