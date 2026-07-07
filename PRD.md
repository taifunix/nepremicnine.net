# Product Requirements Document

## Product

A local Telegram-first real estate monitoring assistant for rental listings from `nepremicnine.net`.

## User Goal

The user wants to avoid manually checking many saved searches and instead receive fresh, relevant rental listing cards in Telegram, make decisions from the phone, and keep notes/history for later.

## MVP Scope

The MVP must:

- Poll configured rental search URLs.
- Store all processed listings in a local database for later rule tuning.
- Detect new listings and price changes.
- Parse detail pages, not just search cards.
- Extract useful fields from title, attributes, description, and metadata.
- Classify bedroom count, utilities status, seller type, location match, and secondary land/garden information.
- Send Telegram cards for relevant new listings and price changes.
- Allow mobile actions: save, mark expensive, reject.
- Store reply notes per listing.
- Provide menu views for new, saved, expensive, and settings.
- Run regular polling locally without visible windows.
- Alert when polling fails or recovers.

## Non-Goals For Current MVP

- Public multi-user SaaS deployment.
- Web admin UI.
- Cloud hosting.
- Payment/billing.
- Owner-site integration/API partnership.
- ML-based semantic classifier.
- Bypassing Cloudflare as a product feature.

## Data Sources

Primary source is `nepremicnine.net`.

Search sources are configured as site-filtered URLs:

- `full_url` for initial full backfill.
- `daily_url` for recurring 24-hour polling.

If `daily_url` is omitted, it is derived by adding `24ur/` after the site root.

## Core Events

- New listing: a site id appears in search results and is not present in local DB.
- Price drop: current parsed price is lower than stored price.
- Price rise: current parsed price is higher than stored price.
- Audit miss: daily search page shows an id that is not in DB after polling.

## Listing Classification Requirements

Bedrooms:

- Prefer structured site field when available.
- Also inspect title, body description, `itemprop=description`, and detail tab text.
- Distinguish bedrooms from rooms.
- `2,5-sobno` or higher usually implies two bedrooms.
- `2-sobno` can be ambiguous and may be marked as maybe/sporno.

Utilities:

- Detect whether utilities/stroški are included, partially included, separate, or unknown.
- Do not display unknown utilities in cards.

Seller:

- Private if `ZASEBNA PONUDBA` appears in contact/agency block.
- Otherwise agency by default.
- Chat settings can filter new cards by all/private/agency.

Location:

- Use site location filters in search URLs.
- Apply local blacklists inside broad site regions.
- Coordinates are not generally available and are not relied on in MVP.

Secondary features:

- Land/garden information is extracted as a display-only card line.
- It is not yet stored as a structured first-class DB column.

## Telegram UX Requirements

Main menu:

- `Новые`
- `Избранное`
- `Дорогие`
- `Настройки`

Cards:

- One listing per Telegram message.
- Russian labels.
- Bold values, plain labels.
- Unknown fields omitted.
- Link text: `Смотреть на Nepremicnine.net`.
- Date at the bottom.
- Card messages auto-delete after 90 minutes.

Actions:

- `Сохранить` moves listing to favorites.
- `Дорого` moves listing to expensive and hides from new.
- `Не подходит` rejects listing and hides from new.
- Replying to a card stores a note.

Visibility:

- `Новые` applies current chat filters.
- `Избранное` ignores current chat filters.
- `Дорогие` ignores current chat filters.
- Rejected listings can reappear when price changes.

Settings:

- Price min/max.
- Area min/max.
- Bedroom min/max.
- Include/exclude maybe/sporno.
- Seller type: all/private/agency.

Region settings are planned but not implemented yet.

## Reliability Requirements

Scheduled polling must:

- Run every 15 minutes locally.
- Use a lock file to prevent overlapping runs.
- Log all runs.
- Send Telegram alert on first failure.
- Repeat alert on every third consecutive failure.
- Send recovery alert after successful run following failures.
- Send daily heartbeat on the first successful run each day.

Audit recovery must:

- Compare daily search result ids to DB ids.
- Retry missing detail pages.
- Alert after repeated recovery failures.

## Acceptance Checks

- `python -m pytest tests/test_bot.py tests/test_runner.py tests/test_config.py tests/test_storage.py -q` passes.
- Scheduled task `NepremicnineDailyPoll` exists and action points to hidden VBS runner.
- `data/poll.log` shows successful daily polling with `errors=0`.
- Telegram bot responds to menu buttons.
- New/saved/expensive visibility rules match this PRD.

