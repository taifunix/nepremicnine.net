# Nepremicnine Bot

Nepremicnine Bot is a local MVP for monitoring rental listings on `nepremicnine.net`, storing parsed listing data in SQLite, and managing listing decisions from Telegram.

It is designed for personal use first: one local machine, one SQLite database, one Telegram bot/group, and scheduled background polling on Windows.

## What It Does

The bot automates this workflow:

1. Poll configured `nepremicnine.net` search pages.
2. Open each listing detail page.
3. Store the listing, raw-ish parsed text, extracted facts, price history, notes, and status in SQLite.
4. Detect new listings and price changes.
5. Send Telegram listing cards for actionable events.
6. Let you save, reject, mark as expensive, and add notes directly from Telegram.
7. Run regular polling in the background and alert you if polling stops working.

## Current MVP Features

- Full backfill polling from regular search URLs.
- Daily polling from 24-hour search URLs.
- Search pagination support.
- Detail-page parsing.
- SQLite persistence for listings, snapshots, extracted facts, evaluations, notes, statuses, price history, chat settings, and Telegram message mappings.
- New listing detection.
- Price drop and price rise detection.
- Audit recovery for listings that appear in daily search results but are missing from the database.
- Telegram menu: `Новые`, `Избранное`, `Дорогие`, `Настройки`.
- Per-listing Telegram cards with inline buttons.
- Reply-to-card notes.
- Per-chat filters for new cards.
- Hidden Windows scheduled polling every 15 minutes.
- Polling health alerts in Telegram.

## Important Limitations

- This is a local MVP, not a hosted service.
- It depends on browser access to `nepremicnine.net`.
- Site access can fail because of Cloudflare, proxy problems, network issues, or site changes.
- The parser and classifiers are rule-based and should be improved as more local data is collected.
- Region filtering in Telegram settings is planned but not implemented yet.

## Architecture

The project is a Python package under `src/nepremicnine_bot`.

- `config.py` loads `.env`, search sources, and rule defaults.
- `fetcher.py` fetches pages using browser/Playwright support and persistent Chrome profiles.
- `parser.py` extracts search cards, detail fields, pagination links, and detail text blocks.
- `classifier.py` extracts and classifies facts such as bedrooms, utilities, seller type, and land/garden hints.
- `storage.py` owns SQLite schema creation, migrations, and queries.
- `runner.py` coordinates polling, event detection, audit recovery, and import flows.
- `bot.py` handles Telegram menu, card rendering, callbacks, notes, settings, batching, and cleanup.
- `notifier.py` sends direct Telegram messages from polling.
- `cli.py` exposes command-line entry points.
- `scripts/` contains Windows operational scripts.

## Runtime Files

These files are local runtime state and must not be committed:

- `.env`
- `data/nepremicnine.sqlite3`
- `data/browser-profile-*`
- `data/session-cookies*.json`
- `data/storage-state*.json`
- `data/poll.log`
- `data/poll-health.json`
- `data/poll.lock`

The repository intentionally ignores `.env`, `data/`, SQLite files, pytest temp folders, Python caches, and local virtual environments.

## Prerequisites

- Windows
- Python 3.12
- Google Chrome
- A Telegram bot token
- A Telegram chat or group id
- Working access to `nepremicnine.net`, currently through the configured proxy setup on this machine

## Installation

From the repository root:

```powershell
cd "<repo-root>"
python -m pip install -e .[dev]
```

Create local configuration:

```powershell
Copy-Item .env.example .env
```

Fill `.env`:

```env
NEPREMICNINE_BOT_TOKEN=<telegram-bot-token>
NEPREMICNINE_CHAT_ID=<telegram-chat-or-group-id>
NEPREMICNINE_DB_PATH=./data/nepremicnine.sqlite3
NEPREMICNINE_POLL_MINUTES=15
NEPREMICNINE_BROWSER_COOKIES_PATH=./data/session-cookies.json
NEPREMICNINE_BROWSER_STORAGE_STATE_PATH=./data/storage-state.json
NEPREMICNINE_SEARCH_SOURCES_FILE=./data/search_sources.json
```

Do not put real credentials into `.env.example`.

## Search Source Configuration

Search sources are stored in `data/search_sources.json`. Use `search_sources.example.json` as the safe template.

Each source can define:

- `name`: stable name used in logs.
- `url`: fallback/base search URL.
- `full_url`: URL used for full backfill.
- `daily_url`: URL used for recurring 24-hour polling.
- `enabled`: whether this source is active.
- `location_blacklist`: local exclusions applied after the site search filter.

Example:

```json
[
  {
    "name": "ljubljana-mesto-stanovanje",
    "url": "https://www.nepremicnine.net/oglasi-oddaja/ljubljana-mesto/stanovanje/cena-do-1000-eur-na-mesec,velikost-od-50-m2/",
    "full_url": "https://www.nepremicnine.net/oglasi-oddaja/ljubljana-mesto/stanovanje/cena-do-1000-eur-na-mesec,velikost-od-50-m2/",
    "daily_url": "https://www.nepremicnine.net/24ur/oglasi-oddaja/ljubljana-mesto/stanovanje/cena-do-1000-eur-na-mesec,velikost-od-50-m2/",
    "enabled": true,
    "location_blacklist": []
  }
]
```

If `daily_url` is omitted, the app derives it by inserting `24ur/` after `https://www.nepremicnine.net/`.

## Browser Session and Proxy

The current local setup uses Chrome with a persistent proxy profile:

- Profile: `data/browser-profile-proxy-interactive`
- Cookies: `data/session-cookies-proxy-interactive.json`
- Storage state: `data/storage-state-proxy-interactive.json`

The proxy itself is read from `NEPREMICNINE_PROXY_FILE`. If the variable is not set, scripts use `data/proxy.txt`. This file is local runtime data and should not be committed.

Warm or check the browser session:

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\warm-browser.ps1" -UseProxy
powershell -ExecutionPolicy Bypass -File ".\scripts\check-session.ps1" -UseProxy
```

Use warm-browser when the site starts showing Cloudflare checks again or when the browser profile needs to be refreshed.

## Manual Polling

Full backfill:

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\poll.ps1" -UseProxy -Window full
```

Daily polling with audit recovery:

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\poll.ps1" -UseProxy -Window daily -AuditRecover
```

Daily polling is the normal recurring mode. Full polling is for initial backfill or explicit resyncs.

## Scheduled Background Polling

Regular polling is installed as a Windows Scheduled Task:

```text
NepremicnineDailyPoll
```

Install or update it:

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\install-poll-task.ps1"
```

The task runs hidden:

```text
wscript.exe scripts/run-daily-poll-hidden.vbs
```

That VBS wrapper starts hidden PowerShell, which runs:

```text
scripts/run-daily-poll.ps1 -> scripts/poll.ps1 -Window daily -UseProxy -AuditRecover
```

Inspect task state:

```powershell
Get-ScheduledTask -TaskName NepremicnineDailyPoll
Get-ScheduledTaskInfo -TaskName NepremicnineDailyPoll
```

Run it once immediately:

```powershell
Start-ScheduledTask -TaskName NepremicnineDailyPoll
```

Uninstall it:

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\uninstall-poll-task.ps1"
```

## Polling Health Monitoring

The scheduled wrapper writes:

- `data/poll.log`
- `data/poll-health.json`

Read recent logs:

```powershell
Get-Content ".\data\poll.log" -Tail 80
```

Read health state:

```powershell
Get-Content ".\data\poll-health.json" -Raw
```

Health behavior:

- First consecutive polling failure sends a Telegram alert.
- Every third consecutive failure sends another alert.
- First successful run after failures sends a recovery alert.
- First successful run of each day sends a heartbeat alert.
- A lock file prevents overlapping polling runs.

This is how you know when fresh listings may not be arriving.

## Starting the Telegram Bot

The Telegram bot process is separate from scheduled polling.

Manual foreground start:

```powershell
$env:PYTHONPATH = (Join-Path (Resolve-Path ".").Path "src")
python -m nepremicnine_bot.cli bot
```

If the package was installed with `pip install -e .[dev]`, `PYTHONPATH` is usually not needed.

## Telegram User Workflow

The bot menu contains:

- `Новые`
- `Избранное`
- `Дорогие`
- `Настройки`

### Новые

Shows new/current listing candidates.

This section applies current chat filters:

- price range
- area range
- bedroom range
- include/exclude uncertain bedroom matches
- seller type: all/private/agency

Saved, rejected, and expensive listings are hidden from `Новые`.

### Избранное

Shows listings marked as saved.

This section does not apply current chat filters. This is intentional: if you saved a listing earlier, it should remain visible even after changing filters.

Saved listing cards include accumulated notes.

### Дорогие

Shows listings marked as expensive.

This section does not apply current chat filters, for the same reason as favorites.

### Настройки

Lets you configure filters for `Новые`.

Current settings:

- price min/max
- area min/max
- bedrooms min/max
- include uncertain/sporno listings
- seller type

Region settings are planned for later.

## Listing Card Actions

Each card has inline buttons:

- `Сохранить`: mark as saved and keep in favorites.
- `Дорого`: mark as expensive and hide from new cards.
- `Не подходит`: mark as rejected and hide from new cards.

Card messages are automatically deleted from chat after 90 minutes to keep the group clean.

## Notes

Reply to a listing card in Telegram to save a note for that listing.

Examples:

- called, no answer
- viewed, not suitable
- scheduled viewing for Friday
- agent confirmed utilities are separate

Notes are stored in SQLite and shown with saved listings.

## Price Changes

The polling pipeline detects both price drops and price rises.

Price-change cards include the current price and previous price.

Rejected listings may reappear when price changes, because a changed price can make a previously rejected option worth reviewing again.

## Card Format

Telegram cards are HTML-formatted.

Typical fields:

- title summary
- badge such as `НОВОЕ` or `ЦЕНА ИЗМЕНИЛАСЬ`
- region
- price
- seller type
- area
- source room count
- inferred bedrooms
- utilities status
- land/garden hint
- link to `Nepremicnine.net`
- date at the bottom

Unknown values are omitted.

## SQLite Data Model

Main tables:

- `listings`: identity, URL, title, location, current price, area.
- `price_history`: previous/current price observations.
- `listing_snapshots`: parsed search/detail data and content hashes.
- `listing_features`: extracted text facts.
- `listing_evaluations`: classifier outputs and pass flags.
- `listing_status`: `new`, `saved`, `rejected`, `expensive`.
- `listing_notes`: notes entered through Telegram or commands.
- `telegram_message_mappings`: maps Telegram message ids to listings.
- `chat_settings`: per-chat filter settings.
- `chat_input_state`: temporary settings input state.
- `audit_recovery_failures`: missed-listing retry state.

## Testing

Main regression suite:

```powershell
$base = Join-Path $env:TEMP "realestate-pytest"
python -m pytest tests/test_bot.py tests/test_runner.py tests/test_config.py tests/test_storage.py -q --basetemp $base
```

Full test suite:

```powershell
$base = Join-Path $env:TEMP "realestate-pytest-full"
python -m pytest -q --basetemp $base
```

Use `%TEMP%` for `--basetemp` to avoid creating local `.pytest-tmp*` folders in the repository.

## Troubleshooting

### Polling fails with `ERR_NETWORK_ACCESS_DENIED`

Direct access from this machine is not usable. Run with `-UseProxy`.

### Polling fails with `ERR_PROXY_CONNECTION_FAILED`

The proxy endpoint or auth may be temporarily unavailable. The scheduled health monitor should alert in Telegram if this happens during background polling.

### Cloudflare appears again

Run:

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\warm-browser.ps1" -UseProxy
```

Then complete the browser check if a visible browser opens.

### Scheduled task opens a PowerShell window

The task action should be:

```text
wscript.exe "...\scripts\run-daily-poll-hidden.vbs"
```

If it points directly to `powershell.exe`, reinstall:

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\install-poll-task.ps1"
```

### Telegram bot does not respond

Check whether the bot process is running:

```powershell
Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*nepremicnine_bot.cli bot*' }
```

Restart manually if needed:

```powershell
$env:PYTHONPATH = (Join-Path (Resolve-Path ".").Path "src")
python -m nepremicnine_bot.cli bot
```

### `.pytest-tmp*` folders cannot be deleted

Some old pytest temp folders may have broken Windows ACLs. They are ignored by git. Delete manually with admin/owner permissions if you want to physically clean them.

## What Not To Commit

Do not commit:

- `.env`
- `data/`
- SQLite databases
- cookies
- Playwright/Chrome profiles
- proxy files
- logs
- `.pytest_cache/`
- `.pytest-tmp*/`
- `__pycache__/`
- `*.egg-info/`

## Documentation For Future Work

- `AGENTS.md`: minimal context routing for Codex sessions.
- `PRD.md`: product requirements and scope.
- `Progress.md`: current implementation state and next work.
- `docs/superpowers/`: historical implementation specs and plans. Load only when working on that area.
