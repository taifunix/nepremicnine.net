param(
    [string]$Url = 'https://www.nepremicnine.net/nepremicnine.html',
    [switch]$UseProxy,
    [switch]$ResetProfile
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$python = if ($env:PYTHON) { $env:PYTHON } else { 'python' }
$proxyFile = if ($env:NEPREMICNINE_PROXY_FILE) { $env:NEPREMICNINE_PROXY_FILE } else { Join-Path $repoRoot 'data\proxy.txt' }
$proxyProfileDir = Join-Path $repoRoot 'data\browser-profile-proxy-interactive'
$proxyCookiesPath = Join-Path $repoRoot 'data\session-cookies-proxy-interactive.json'
$proxyStoragePath = Join-Path $repoRoot 'data\storage-state-proxy-interactive.json'

$env:NEPREMICNINE_BROWSER_HEADLESS = 'true'
$env:NEPREMICNINE_BROWSER_CHANNEL = 'chrome'
$env:NEPREMICNINE_BROWSER_PROXY = ''

$proxy = $null
if ($UseProxy) {
    $proxy = Get-Content $proxyFile | Where-Object { $_.Trim() } | Select-Object -First 1
    if (-not $proxy) { throw "Proxy file is empty: $proxyFile" }
    $env:NEPREMICNINE_BROWSER_PROXY = $proxy
    $env:NEPREMICNINE_BROWSER_USER_DATA_DIR = $proxyProfileDir
    $env:NEPREMICNINE_BROWSER_COOKIES_PATH = $proxyCookiesPath
    $env:NEPREMICNINE_BROWSER_STORAGE_STATE_PATH = $proxyStoragePath

    if ($ResetProfile) {
        Remove-Item -LiteralPath $proxyProfileDir -Recurse -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $proxyCookiesPath -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $proxyStoragePath -Force -ErrorAction SilentlyContinue
    }

    Write-Host "Using proxy: $proxy" -ForegroundColor Cyan
    Write-Host "Proxy profile: $proxyProfileDir" -ForegroundColor Cyan
    if ($ResetProfile) {
        Write-Host 'Proxy profile reset requested' -ForegroundColor Yellow
    }
} else {
    Write-Host 'Using direct connection (no proxy)' -ForegroundColor Cyan
}

& $python -m nepremicnine_bot.cli check-session $Url
