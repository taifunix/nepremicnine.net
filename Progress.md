# Progress

Last updated: 2026-07-07

## Current State

The local MVP is functional.

Implemented:

- Python package scaffold with CLI.
- Playwright/Chrome browser fetcher with persistent profile, proxy support, cookie/storage state handling.
- Search result parsing with pagination.
- Detail page parsing with title, description, attributes, agency block, room count, region/date fields, and map-related text where available.
- Text fact extraction for bedrooms, utilities, heating, seller type, land/garden.
- SQLite persistence for listings, snapshots, features, evaluations, price history, statuses, notes, Telegram message mappings, chat settings, and audit recovery failures.
- Full and daily polling windows.
- Audit recovery for missing daily search results.
- Telegram notifier for polling events.
- Telegram bot with menu, listing cards, inline actions, reply notes, settings flow, batching, rate-limit handling, and card cleanup.
- Windows scheduled polling every 15 minutes.
- Hidden scheduled polling via `run-daily-poll-hidden.vbs`.
- Polling health monitor with Telegram failure/recovery/heartbeat alerts.

## Current Runtime

Scheduled task:

- Name: `NepremicnineDailyPoll`
- Action: `wscript.exe "<repo-root>\scripts\run-daily-poll-hidden.vbs"`
- Expected command path: VBS -> hidden PowerShell -> `run-daily-poll.ps1` -> `poll.ps1 -Window daily -UseProxy -AuditRecover`
- Log: `data/poll.log`
- Health state: `data/poll-health.json`

Telegram bot:

- Run manually as `python -m nepremicnine_bot.cli bot` with `PYTHONPATH=src`, or via the existing hidden process if already started.
- Bot menu is persistent in the group.

## Latest Verified Checks

- Main regression suite passed after the saved/expensive filter regression:
  `81 passed in 7.13s`
- Hidden scheduled task was verified after conversion to `wscript.exe`.
- Scheduled polling log showed successful proxy daily run with audit recovery and `errors=0`.

## Important Decisions

- Bot settings filter only `Новые`.
- `Избранное` and `Дорогие` ignore current settings so old decisions remain visible.
- Cards auto-delete after 90 minutes to avoid Telegram clutter and old-message edit limits.
- Polling stores all processed listings from configured source URLs, not only cards currently shown by Telegram filters.
- `data/` is local runtime state and must not be committed.
- `.env.example` must never contain real Telegram credentials.

## Known Issues / Local Cleanup

Some `.pytest-tmp*` directories remain with Windows ACL `Access is denied`. They are ignored by `.gitignore`, but physical deletion may require manual admin/owner cleanup.

Do not delete:

- `.env`
- `data/`
- browser profiles
- cookies/storage state
- SQLite DB

Generated artifacts already safe to delete when accessible:

- `.pytest_cache/`
- `.pytest-tmp*/`
- `src/nepremicnine_bot.egg-info/`
- `__pycache__/`

## Recommended Next Features

1. Add rejected-list menu with restore/save actions.
2. Add region filter to Telegram settings.
3. Add manual “import by direct listing URL”.
4. Improve utilities and bedroom classifier on larger stored corpus.
5. Add scheduler install status command or bot admin health command.
6. Split large `bot.py` and `storage.py` when changing them next, because they are now broad modules.

## Useful Commands

Run tests:

```powershell
$base = Join-Path $env:TEMP "realestate-pytest"
python -m pytest tests/test_bot.py tests/test_runner.py tests/test_config.py tests/test_storage.py -q --basetemp $base
```

Inspect task:

```powershell
Get-ScheduledTask -TaskName NepremicnineDailyPoll
Get-ScheduledTaskInfo -TaskName NepremicnineDailyPoll
Get-Content ".\data\poll.log" -Tail 80
```

Run daily poll once:

```powershell
powershell -ExecutionPolicy Bypass -File ".\scripts\poll.ps1" -UseProxy -Window daily -AuditRecover
```
