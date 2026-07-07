# Seller Filter And Search Sources Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a seller-type filter to Telegram chat settings and prepare search source JSON for full backfill plus later daily polling.

**Architecture:** Extend `chat_settings` with one new persisted selector and apply it when rendering `Новые`. Extend `SearchSource` with explicit `full_url` and `daily_url` fields while keeping `url` as the active polling URL for the initial backfill phase.

**Tech Stack:** Python 3.12, SQLite, Pydantic, pytest

---

### Task 1: Seller Type Chat Setting

**Files:**
- Modify: `src/nepremicnine_bot/storage.py`
- Modify: `src/nepremicnine_bot/bot.py`
- Test: `tests/test_storage.py`
- Test: `tests/test_bot.py`

- [ ] Add failing tests for persisted default/update behavior, settings text, settings callback cycling, and seller filtering in `Новые`.
- [ ] Run the targeted tests and confirm they fail for missing `seller_type` behavior.
- [ ] Add SQLite schema + migration support for `seller_type`.
- [ ] Add Telegram settings text, inline button, callback cycle, reset behavior, and filter matching.
- [ ] Re-run targeted tests and confirm they pass.

### Task 2: Search Source Full/Daily URLs

**Files:**
- Modify: `src/nepremicnine_bot/config.py`
- Modify: `tests/test_config.py`
- Modify: `search_sources.example.json`
- Create: `data/search_sources.json`
- Modify: `README.md`

- [ ] Add failing tests for `full_url` and `daily_url` loading through direct settings and JSON file loading.
- [ ] Run the targeted config tests and confirm they fail.
- [ ] Extend `SearchSource` with explicit `full_url` and `daily_url`, defaulting `full_url` to `url` and building a 24-hour variant for `daily_url` when missing.
- [ ] Add the six real search source entries from `data/search.txt` into `data/search_sources.json`.
- [ ] Update example config and README notes so the current poller still uses `url` for the full backfill phase.

### Task 3: Verification

**Files:**
- Test: `tests/test_bot.py`
- Test: `tests/test_storage.py`
- Test: `tests/test_config.py`
- Test: `tests/test_runner.py`

- [ ] Run the targeted regression tests for seller filter and search sources.
- [ ] Run the broader affected test suite.
- [ ] Review the generated JSON and env wiring to confirm the poller now has a real source file path.
