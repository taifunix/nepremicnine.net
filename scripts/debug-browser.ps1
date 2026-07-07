param(
    [string]$Url = 'https://www.nepremicnine.net/nepremicnine.html'
)

$ErrorActionPreference = 'Stop'
$python = if ($env:PYTHON) { $env:PYTHON } else { 'python' }
Write-Host "Direct browser debug starting..." -ForegroundColor Cyan
Write-Host "URL: $Url" -ForegroundColor Cyan

@"
from nepremicnine_bot.fetcher import BrowserSiteFetcher

fetcher = BrowserSiteFetcher(user_data_dir="./data/browser-profile", headless=False, channel="chrome")
print("fetcher.headless =", fetcher.headless)
print("fetcher.channel =", fetcher.channel)
fetcher.warm_session(r"$Url")
print("warm_session returned")
"@ | & $python -
