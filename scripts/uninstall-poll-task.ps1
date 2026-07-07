param(
    [string]$TaskName = 'NepremicnineDailyPoll'
)

$ErrorActionPreference = 'Stop'

if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    "Removed scheduled task: $TaskName"
} else {
    "Scheduled task not found: $TaskName"
}
