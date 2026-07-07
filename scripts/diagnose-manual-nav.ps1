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
$env:NEPREMICNINE_BROWSER_USER_DATA_DIR = Join-Path $env:TEMP 'nep-browser-proxy-manual-debug'
$env:NEPREMICNINE_BROWSER_COOKIES_PATH = Join-Path $env:TEMP 'nep-session-cookies-proxy-manual-debug.json'
$env:NEPREMICNINE_BROWSER_STORAGE_STATE_PATH = Join-Path $env:TEMP 'nep-storage-state-proxy-manual-debug.json'

Write-Host 'Starting manual navigation diagnostic...' -ForegroundColor Cyan
if ($UseProxy) {
    Write-Host "Using proxy: $proxy" -ForegroundColor Cyan
} else {
    Write-Host 'Using direct connection (no proxy)' -ForegroundColor Cyan
}
Write-Host 'After the initial load, manually open a few sites in the same tab.' -ForegroundColor Yellow
Write-Host 'The script will log navigation changes and request failures for 60 seconds.' -ForegroundColor Yellow

@"
import shutil
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

with fetcher._open_context() as playwright:
    context = fetcher._launch_browser(playwright)
    try:
        page = context.new_page()

        def log_nav(frame):
            if frame == page.main_frame:
                print(f'[nav] {page.url}')

        def log_req_failed(request):
            failure = request.failure
            text = failure if isinstance(failure, str) else getattr(failure, 'error_text', failure)
            print(f'[requestfailed] {request.method} {request.url} -> {text}')

        def log_page_error(err):
            print(f'[pageerror] {err}')

        page.on('framenavigated', log_nav)
        page.on('requestfailed', log_req_failed)
        page.on('pageerror', log_page_error)

        page.goto('https://example.com', wait_until='domcontentloaded', timeout=30000)
        print(f'[ready] initial page {page.url} title={page.title()!r}')
        print('[ready] manual test window: 60 seconds')

        last_url = page.url
        for second in range(60):
            current_url = page.url
            if current_url != last_url:
                print(f'[poll] url changed -> {current_url}')
                last_url = current_url
            try:
                title = page.title()
            except Exception as exc:
                title = f'<title-error {type(exc).__name__}: {exc}>'
            print(f'[tick {second + 1:02d}] url={current_url} title={title!r}')
            time.sleep(1)
    finally:
        try:
            context.close()
        except Exception:
            pass
"@ | & $python -
