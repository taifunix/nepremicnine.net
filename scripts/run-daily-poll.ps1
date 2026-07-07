param(
    [switch]$NoProxy,
    [switch]$NoAuditRecover,
    [switch]$DryRunNotifications
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$dataDir = Join-Path $repoRoot 'data'
$logPath = Join-Path $dataDir 'poll.log'
$lockPath = Join-Path $dataDir 'poll.lock'
$healthPath = Join-Path $dataDir 'poll-health.json'
$envPath = Join-Path $repoRoot '.env'

New-Item -ItemType Directory -Path $dataDir -Force | Out-Null

function Write-PollLog {
    param([string]$Message)
    $stamp = Get-Date -Format 'yyyy-MM-dd HH:mm:ss'
    Add-Content -Path $logPath -Encoding UTF8 -Value "[$stamp] $Message"
}

function Read-DotEnvValue {
    param([string]$Name)
    if (-not (Test-Path -LiteralPath $envPath)) {
        return $null
    }
    $line = Get-Content -LiteralPath $envPath -Encoding UTF8 |
        Where-Object { $_ -match "^\s*$([regex]::Escape($Name))\s*=" } |
        Select-Object -First 1
    if (-not $line) {
        return $null
    }
    return ($line -replace "^\s*$([regex]::Escape($Name))\s*=\s*", '').Trim().Trim('"')
}

function Read-PollHealth {
    if (-not (Test-Path -LiteralPath $healthPath)) {
        return [pscustomobject]@{
            consecutiveFailures = 0
            lastSuccessAt = $null
            lastFailureAt = $null
            lastAlertAt = $null
            lastHeartbeatDate = $null
        }
    }
    return Get-Content -LiteralPath $healthPath -Encoding UTF8 -Raw | ConvertFrom-Json
}

function Save-PollHealth {
    param([object]$Health)
    $Health | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath $healthPath -Encoding UTF8
}

function Send-PollAlert {
    param([string]$Text)
    if ($DryRunNotifications) {
        Write-PollLog "DRY_ALERT: $Text"
        return
    }

    $token = $env:NEPREMICNINE_BOT_TOKEN
    if (-not $token) {
        $token = Read-DotEnvValue 'NEPREMICNINE_BOT_TOKEN'
    }
    $chatId = $env:NEPREMICNINE_CHAT_ID
    if (-not $chatId) {
        $chatId = Read-DotEnvValue 'NEPREMICNINE_CHAT_ID'
    }
    if (-not $token -or -not $chatId) {
        Write-PollLog 'ALERT_SKIPPED: Telegram token/chat id are not configured'
        return
    }

    try {
        Invoke-RestMethod `
            -Method Post `
            -Uri "https://api.telegram.org/bot$token/sendMessage" `
            -ContentType 'application/json; charset=utf-8' `
            -Body (@{
                chat_id = $chatId
                text = $Text
                disable_web_page_preview = $true
            } | ConvertTo-Json -Compress) | Out-Null
        Write-PollLog 'ALERT_SENT'
    } catch {
        Write-PollLog "ALERT_FAILED: $($_.Exception.Message)"
    }
}

function Get-PollSummary {
    param([object[]]$Output)
    $total = $Output | Where-Object { "$_" -like 'Total:*' } | Select-Object -Last 1
    $sent = $Output | Where-Object { "$_" -like 'Sent * notifications' } | Select-Object -Last 1
    return (@($total, $sent) | Where-Object { $_ }) -join "`n"
}

function Get-ConsecutiveFailures {
    param([object]$Health)
    if ($null -eq $Health.consecutiveFailures) {
        return 0
    }
    return [int]$Health.consecutiveFailures
}

$lockCreated = $false
$health = Read-PollHealth
try {
    if (Test-Path -LiteralPath $lockPath) {
        $lockAge = (Get-Date) - (Get-Item -LiteralPath $lockPath).LastWriteTime
        if ($lockAge.TotalHours -lt 2) {
            Write-PollLog "SKIP: previous polling lock exists: $lockPath"
            exit 0
        }
        Write-PollLog "WARN: removing stale polling lock older than 2 hours"
        Send-PollAlert "NEPREMICNINE POLLING WARNING`nStale lock older than 2 hours was removed.`nPath: $lockPath"
        Remove-Item -LiteralPath $lockPath -Force
    }

    New-Item -ItemType File -Path $lockPath -Value $PID -ErrorAction Stop | Out-Null
    $lockCreated = $true

    $args = @('-ExecutionPolicy', 'Bypass', '-File', (Join-Path $PSScriptRoot 'poll.ps1'), '-Window', 'daily')
    if (-not $NoProxy) {
        $args += '-UseProxy'
    }
    if (-not $NoAuditRecover) {
        $args += '-AuditRecover'
    }

    Write-PollLog "START: powershell $($args -join ' ')"
    $output = & powershell @args 2>&1
    $exitCode = $LASTEXITCODE
    foreach ($line in $output) {
        Write-PollLog "OUT: $line"
    }
    if ($exitCode -ne 0) {
        throw "poll.ps1 failed with exit code $exitCode"
    }
    $previousFailures = Get-ConsecutiveFailures $health
    $health.consecutiveFailures = 0
    $health.lastSuccessAt = (Get-Date).ToString('s')

    $summary = Get-PollSummary $output
    if ($previousFailures -gt 0) {
        Send-PollAlert "NEPREMICNINE POLLING RECOVERED`nPrevious consecutive failures: $previousFailures`n$summary"
    }

    $today = Get-Date -Format 'yyyy-MM-dd'
    if ($health.lastHeartbeatDate -ne $today) {
        $health.lastHeartbeatDate = $today
        Send-PollAlert "NEPREMICNINE POLLING OK`nDaily heartbeat: polling is running.`n$summary"
    }

    Save-PollHealth $health
    Write-PollLog "DONE"
} catch {
    $health.consecutiveFailures = (Get-ConsecutiveFailures $health) + 1
    $health.lastFailureAt = (Get-Date).ToString('s')
    $message = $_.Exception.Message
    Save-PollHealth $health
    Write-PollLog "ERROR: $message"
    if ($health.consecutiveFailures -eq 1 -or ($health.consecutiveFailures % 3) -eq 0) {
        $health.lastAlertAt = (Get-Date).ToString('s')
        Save-PollHealth $health
        Send-PollAlert "NEPREMICNINE POLLING FAILED`nConsecutive failures: $($health.consecutiveFailures)`nError: $message`nLog: $logPath"
    }
    exit 1
} finally {
    if ($lockCreated -and (Test-Path -LiteralPath $lockPath)) {
        Remove-Item -LiteralPath $lockPath -Force -ErrorAction SilentlyContinue
    }
}
