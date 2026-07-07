param(
    [string]$Url,
    [int]$Count = 5,
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

if (-not $Url) {
    throw 'Url is required.'
}

$env:NEPREMICNINE_BROWSER_CHANNEL = 'chrome'
$env:NEPREMICNINE_BROWSER_HEADLESS = 'true'
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
}

Write-Host 'Exporting Nepremicnine pages...' -ForegroundColor Cyan
Write-Host "URL: $Url" -ForegroundColor Cyan
Write-Host "Count: $Count" -ForegroundColor Cyan
if ($UseProxy) {
    Write-Host "Using proxy: $proxy" -ForegroundColor Cyan
    Write-Host "Proxy profile: $proxyProfileDir" -ForegroundColor Cyan
} else {
    Write-Host 'Using direct connection (no proxy)' -ForegroundColor Cyan
}

@"
import json
from pathlib import Path

from nepremicnine_bot.fetcher import build_fetcher
from nepremicnine_bot.parser import parse_search_results

url = r'''$Url'''
count = int(r'''$Count''')
repo_root = Path(r'''$repoRoot''')
search_export_path = repo_root / 'data' / 'export-search-page.html'
details_dir = repo_root / 'data' / 'exported-details'
manifest_path = repo_root / 'data' / 'exported-details-manifest.json'
search_export_path.parent.mkdir(parents=True, exist_ok=True)
details_dir.mkdir(parents=True, exist_ok=True)

fetcher = build_fetcher(
    'browser',
    browser_user_data_dir=str(repo_root / 'data' / 'browser-profile-proxy-interactive'),
    browser_headless=True,
    browser_channel='chrome',
    browser_proxy=r'''$proxy'''.strip() or None,
    browser_cookies_path=str(repo_root / 'data' / 'session-cookies-proxy-interactive.json'),
    browser_storage_state_path=str(repo_root / 'data' / 'storage-state-proxy-interactive.json'),
)

search_html = fetcher.fetch_text(url)
search_export_path.write_text(search_html, encoding='utf-8')
results = parse_search_results(search_html)
manifest = []
for item in results[:count]:
    detail_html = fetcher.fetch_text(str(item['url']))
    target = details_dir / f"{item['site_id']}.html"
    target.write_text(detail_html, encoding='utf-8')
    manifest.append({
        'site_id': item['site_id'],
        'url': item['url'],
        'title': item['title'],
        'price_text': item['price_text'],
        'area_text': item['area_text'],
        'location_text': item['location_text'],
        'html_path': str(target.relative_to(repo_root)),
    })

manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
print(f'search_saved={search_export_path.relative_to(repo_root)}')
print(f'manifest_saved={manifest_path.relative_to(repo_root)}')
print(f'exported_details={len(manifest)}')
for row in manifest:
    print(json.dumps(row, ensure_ascii=False))
"@ | & $python -
