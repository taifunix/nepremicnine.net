# Seller Filter And Search Sources Design

## Goal

Add one chat-level Telegram setting for seller type filtering and prepare search source configuration for two polling phases:
- initial full backfill
- later daily polling

## Decisions

- Seller type uses one enum-like setting: `all`, `private`, `agency`.
- The setting is shown in Telegram `Настройки` and cycles through values via one inline button.
- The seller filter applies to `Новые` cards only. `Избранное` remains a history view.
- Search source JSON stores `url`, `full_url`, and `daily_url`.
- Current polling keeps using `url`, and for the initial rollout `url` equals `full_url`.
- `daily_url` is stored now for the later phase switch without changing the file format again.

## Data Changes

- `chat_settings` gets a new column `seller_type TEXT NOT NULL DEFAULT 'all'`.
- Existing SQLite databases are migrated in place on startup.

## Non-Goals

- Automatic switching from full scan to daily scan.
- `?last=2/3/7/31` fallback logic.
- Region filters and location blacklists in bot settings.
