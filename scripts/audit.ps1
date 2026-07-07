param(
    [switch]$UseProxy,
    [ValidateSet('full', 'daily')]
    [string]$Window = 'full'
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$python = if ($env:PYTHON) { $env:PYTHON } else { 'python' }
$proxyFile = if ($env:NEPREMICNINE_PROXY_FILE) { $env:NEPREMICNINE_PROXY_FILE } else { Join-Path $repoRoot 'data\proxy.txt' }
$proxyProfileDir = Join-Path $repoRoot 'data\browser-profile-proxy-interactive'
$proxyCookiesPath = Join-Path $repoRoot 'data\session-cookies-proxy-interactive.json'
$proxyStoragePath = Join-Path $repoRoot 'data\storage-state-proxy-interactive.json'

$env:NEPREMICNINE_BROWSER_CHANNEL = 'chrome'
$env:NEPREMICNINE_BROWSER_PROXY = ''
$env:PYTHONPATH = Join-Path $repoRoot 'src'

Set-Location $repoRoot

if ($UseProxy) {
    $proxy = Get-Content $proxyFile | Where-Object { $_.Trim() } | Select-Object -First 1
    if (-not $proxy) { throw "Proxy file is empty: $proxyFile" }
    $env:NEPREMICNINE_BROWSER_PROXY = $proxy
    $env:NEPREMICNINE_BROWSER_USER_DATA_DIR = $proxyProfileDir
    $env:NEPREMICNINE_BROWSER_COOKIES_PATH = $proxyCookiesPath
    $env:NEPREMICNINE_BROWSER_STORAGE_STATE_PATH = $proxyStoragePath

    Write-Host "Using proxy: $proxy" -ForegroundColor Cyan
    Write-Host "Proxy profile: $proxyProfileDir" -ForegroundColor Cyan
} else {
    Write-Host 'Using direct connection (no proxy)' -ForegroundColor Cyan
}

& $python -m nepremicnine_bot.cli audit --window $Window
