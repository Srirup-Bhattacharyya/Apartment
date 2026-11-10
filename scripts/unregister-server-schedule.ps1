$taskNames = @(
    "Shraddhanjalli Server Start Morning",
    "Shraddhanjalli Server Stop Evening",
    "Shraddhanjalli Server Start Evening",
    "Shraddhanjalli Server Stop Morning"
)

foreach ($taskName in $taskNames) {
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false -ErrorAction SilentlyContinue
}
