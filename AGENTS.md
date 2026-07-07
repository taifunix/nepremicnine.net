# AGENTS.md

This file is the first context document for Codex sessions working in this repository.

## Project Summary

`nepremicnine-bot` is a local Python MVP that monitors `nepremicnine.net` rental listings, stores parsed data in SQLite, and exposes the workflow through Telegram.

Primary runtime is Windows:

- Python 3.12
- SQLite
- Playwright/Chrome via project fetcher
- Telegram Bot API
- Windows Task Scheduler

## Start Here

Read only these files first:

1. `AGENTS.md`
2. `Progress.md`
3. `README.md` sections relevant to the task
4. `PRD.md` only if changing product behavior

Do not load all historical `docs/superpowers/*` by default. Load them only when the task touches that area.

## Context Routing

Use these files depending on the task:

- Telegram UI/cards/settings/notes: `src/nepremicnine_bot/bot.py`, `src/nepremicnine_bot/storage.py`, `tests/test_bot.py`, and `docs/superpowers/specs/2026-07-06-telegram-bot-ui-design.md` if deeper background is needed.
- Polling/audit/price events: `src/nepremicnine_bot/runner.py`, `src/nepremicnine_bot/parser.py`, `src/nepremicnine_bot/fetcher.py`, `tests/test_runner.py`.
- Parsing/classification facts: `src/nepremicnine_bot/parser.py`, `src/nepremicnine_bot/classifier.py`, `tests/test_parser.py`, `tests/test_classifier.py`.
- SQLite schema/query changes: `src/nepremicnine_bot/storage.py`, `tests/test_storage.py`.
- Scheduled polling/Windows ops: `scripts/`, `README.md`, `data/poll.log` if runtime debugging is requested.
- Product scope decisions: `PRD.md`.

## Operational Constraints

- Do not commit `.env`, `data/`, cookies, storage state, browser profiles, proxy files, SQLite DBs, or logs.
- `data/` contains live local state and should not be deleted unless explicitly requested.
- `data/search_sources.json` is local runtime config. `search_sources.example.json` is the safe template.
- Proxy credentials are personal local secrets and should not be copied into tracked files.
- The scheduled task is `NepremicnineDailyPoll`.
- The Telegram bot process may be running separately from scheduled polling.

## Development Rules

- Prefer test-first changes for behavior.
- Run targeted tests for touched areas, then the main regression suite:
  `python -m pytest tests/test_bot.py tests/test_runner.py tests/test_config.py tests/test_storage.py -q --basetemp (Join-Path $env:TEMP "realestate-pytest")`
- Use `apply_patch` for manual edits.
- Do not revert unrelated user changes.
- Keep documentation concise and link to deeper docs rather than duplicating everything.

## Known Local Cleanup Issue

Some `.pytest-tmp*` directories can be left behind with broken Windows ACLs. They are ignored by `.gitignore`. If physical deletion fails with `Access is denied`, tell the user to remove them manually with admin/owner permissions rather than spending time fighting ACLs.

