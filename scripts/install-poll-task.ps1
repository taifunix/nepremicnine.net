[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string]$TaskName = 'NepremicnineDailyPoll',
    [int]$IntervalMinutes = 15,
    [switch]$NoProxy,
    [switch]$NoAuditRecover
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$runner = Join-Path $PSScriptRoot 'run-daily-poll.ps1'
$hiddenRunner = Join-Path $PSScriptRoot 'run-daily-poll-hidden.vbs'

if (-not (Test-Path -LiteralPath $runner)) {
    throw "Runner script not found: $runner"
}
if (-not (Test-Path -LiteralPath $hiddenRunner)) {
    throw "Hidden runner script not found: $hiddenRunner"
}

$argumentParts = @("`"$hiddenRunner`"")
if ($NoProxy) {
    $argumentParts += '-NoProxy'
}
if ($NoAuditRecover) {
    $argumentParts += '-NoAuditRecover'
}

$action = New-ScheduledTaskAction `
    -Execute 'wscript.exe' `
    -Argument ($argumentParts -join ' ') `
    -WorkingDirectory $repoRoot

$trigger = New-ScheduledTaskTrigger `
    -Once `
    -At (Get-Date).AddMinutes(1) `
    -RepetitionInterval (New-TimeSpan -Minutes $IntervalMinutes) `
    -RepetitionDuration (New-TimeSpan -Days 3650)

$settings = New-ScheduledTaskSettingsSet `
    -MultipleInstances IgnoreNew `
    -StartWhenAvailable `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries

$principal = New-ScheduledTaskPrincipal `
    -UserId $env:USERNAME `
    -LogonType Interactive `
    -RunLevel Limited

if ($PSCmdlet.ShouldProcess($TaskName, "Register scheduled polling task every $IntervalMinutes minutes")) {
    Register-ScheduledTask `
        -TaskName $TaskName `
        -Action $action `
        -Trigger $trigger `
        -Settings $settings `
        -Principal $principal `
        -Description 'Poll nepremicnine.net daily search URLs and recover audit misses.' `
        -Force | Out-Null

    Get-ScheduledTask -TaskName $TaskName | Select-Object TaskName, State
}
