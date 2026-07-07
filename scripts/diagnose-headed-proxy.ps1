param(
    [switch]$UseProxy
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
$python = if ($env:PYTHON) { $env:PYTHON } else { 'python' }
$proxyFile = if ($env:NEPREMICNINE_PROXY_FILE) { $env:NEPREMICNINE_PROXY_FILE } else { Join-Path $repoRoot 'data\proxy.txt' }
$proxy = ''
if ($UseProxy) {
    $proxy = Get-Content $proxyFile | Where-Object { $_.Trim() } | Select-Object -First 1
    if (-not $proxy) { throw "Proxy file is empty: $proxyFile" }
}

$env:NEPREMICNINE_BROWSER_HEADLESS = 'false'
$env:NEPREMICNINE_BROWSER_CHANNEL = 'chrome'
$env:NEPREMICNINE_BROWSER_PROXY = $proxy
$env:NEPREMICNINE_BROWSER_USER_DATA_DIR = Join-Path $env:TEMP 'nep-browser-proxy-seq'
$env:NEPREMICNINE_BROWSER_COOKIES_PATH = Join-Path $env:TEMP 'nep-session-cookies-proxy-seq.json'
$env:NEPREMICNINE_BROWSER_STORAGE_STATE_PATH = Join-Path $env:TEMP 'nep-storage-state-proxy-seq.json'

Write-Host 'Starting headed proxy sequence diagnostic...' -ForegroundColor Cyan
if ($UseProxy) {
    Write-Host "Using proxy: $proxy" -ForegroundColor Cyan
} else {
    Write-Host 'Using direct connection (no proxy)' -ForegroundColor Cyan
}
Write-Host "Profile: $env:NEPREMICNINE_BROWSER_USER_DATA_DIR" -ForegroundColor Yellow

@"
import shutil
import tempfile
import time
from pathlib import Path
from nepremicnine_bot.fetcher import BrowserSiteFetcher, parse_proxy_config

proxy_value = r'''$proxy'''.strip()
profile_dir = Path(r'''$env:NEPREMICNINE_BROWSER_USER_DATA_DIR''')
if profile_dir.exists():
    shutil.rmtree(profile_dir, ignore_errors=True)
profile_dir.mkdir(parents=True, exist_ok=True)

proxy_config = parse_proxy_config(proxy_value) if proxy_value else None
fetcher = BrowserSiteFetcher(
    user_data_dir=str(profile_dir),
    headless=False,
    channel='chrome',
    proxy=proxy_config,
    cookies_path=r'''$env:NEPREMICNINE_BROWSER_COOKIES_PATH''',
    storage_state_path=r'''$env:NEPREMICNINE_BROWSER_STORAGE_STATE_PATH''',
    timeout_ms=30000,
)

urls = [
    'https://example.com',
    'https://www.wikipedia.org',
    'https://api.ipify.org?format=json',
    'https://www.nepremicnine.net/',
]

with fetcher._open_context() as playwright:
    context = fetcher._launch_browser(playwright)
    try:
        page = context.new_page()
        for idx, url in enumerate(urls, start=1):
            try:
                page.goto(url, wait_until='domcontentloaded', timeout=30000)
                print(f'{idx}: ok {url} -> {page.url} title={page.title()!r}')
            except Exception as exc:
                print(f'{idx}: fail {url} -> {type(exc).__name__}: {exc}')
            time.sleep(8)
        print('Sequence complete. Browser stays open for 30 seconds; you can also try manual navigation now.')
        for _ in range(30):
            pages = context.pages
            if not pages or pages[0].is_closed():
                break
            time.sleep(1)
    finally:
        try:
            context.close()
        except Exception:
            pass
"@ | & $python -
