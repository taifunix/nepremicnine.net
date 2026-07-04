# Nepremicnine MVP Design

Date: 2026-07-04

## Goal

Build a local MVP agent that monitors `https://www.nepremicnine.net/` for rental listings, filters them using a mix of site-native filters and custom rule-based analysis, sends realtime Telegram alerts for matching private listings, sends a daily digest for matching agency listings, and supports notes and status updates for tracked listings directly through the Telegram bot.

## Scope

In scope:
- Poll multiple saved search URLs on `nepremicnine.net`
- Use the site's native filters, including publication date filters
- Apply custom post-filters for price, area, location blacklist, bedroom inference, and utilities-in-price inference
- Treat private vs agency listings differently
- Notify on new matching listings
- Notify on price drops for already known matching listings
- Store listing state locally
- Allow status updates and notes from Telegram
- Show stored notes and current status from Telegram

Out of scope for MVP:
- Browser automation by default
- Map coordinates and distance calculations
- Full NLP/LLM-based understanding
- A separate web UI
- Complex retry queues or distributed execution
- Generic CRM workflows beyond simple listing tracking

## Operating Model

The service runs locally on the user's machine as a single Python application with a local SQLite database. It is triggered on a schedule for search polling and daily digest creation.

Primary modes:
- `realtime-private`: send immediate alerts for matching private listings
- `daily-agency-digest`: send one daily summary of matching agency listings

## Inputs

### Search Sources

The system uses multiple saved search URLs because one site filter configuration is not enough to represent the full desired search.

Each `search_source` stores:
- `name`
- `url`
- `enabled`
- `mode`: `realtime-private`, `daily-agency-digest`, or both
- `publication_window_strategy`
- `location_blacklist`
- optional future `location_whitelist`

### User Filters

Configurable user filters:
- rental listings only
- price min/max
- area minimum
- multiple site-filtered locations
- custom location blacklist inside those locations
- optional exclusion of agency listings from realtime alerts

### Rule Dictionaries

Rule dictionaries are maintained in config files and used by the classifier.

Initial rule groups:
- `two_bedroom_positive`
- `two_bedroom_negative`
- `utilities_included_positive`
- `utilities_included_partial`
- `utilities_separate_negative`
- `location_blacklist_terms`
- future feature dictionaries such as `has_garden`, `has_land`, `has_yard`

## Functional Requirements

### Search and Fetch

1. The agent polls each enabled search source on a fixed schedule.
2. For each polling run, it applies a short publication date window to reduce result size.
3. The agent first prefers stable XHR/JSON endpoints if the site exposes them.
4. If XHR/JSON is unavailable or incomplete, the agent falls back to HTML parsing.
5. The agent extracts listing cards and a stable site-level identifier for each listing.
6. For new or relevant changed listings, the agent fetches the listing detail page and parses extended data.

### Listing Classification

Each listing is evaluated using rule-based logic over:
- title
- summary/body text
- full description
- visible listing metadata
- `Kontaktni podatki`

Classifier outputs:
- `is_private`: yes/no
- `is_agency`: yes/no
- `two_bedroom_match`: yes/maybe/no
- `utilities_status`: included_yes/partial/no/unknown
- `location_match`: yes/no
- `feature_flags`: extensible dictionary for future criteria
- `passes_realtime`: yes/no
- `passes_daily_digest`: yes/no
- `reason_json`: structured explanation of why it passed or failed

### Private vs Agency Rule

Agency detection is based on a hard rule:
- if `Kontaktni podatki` contains `ZASEBNA PONUDBA`, the listing is private
- otherwise the listing is treated as agency

Behavior:
- private listings can be sent in realtime if they pass all other filters
- agency listings are excluded from realtime by default
- agency listings may appear in the once-daily digest if they pass all other filters

### Bedroom Inference Rule

The system must not rely solely on the site's structured room filters because listing data can be wrong or incomplete.

The classifier inspects title, body, and description for strong and weak signals.

Output logic:
- `yes`: strong positive signal for two bedrooms
- `maybe`: weak or conflicting signals
- `no`: strong negative signal or lack of support

MVP behavior:
- realtime and digest flows include only `two_bedroom_match = yes`
- `maybe` is stored for review but not notified by default

### Utilities Included Rule

The system separately analyzes whether rent includes additional costs such as utilities or internet.

Output logic:
- `included_yes`
- `partial`
- `no`
- `unknown`

This is not a hard filter in MVP unless later configured otherwise. It is included in Telegram output and stored for later review.

### Location Narrowing Rule

Because the site does not provide usable coordinates for the desired precision, geographic narrowing is based on text filtering within the site's broader location filters.

Logic:
- use site-native location filters to define the broad search area
- apply custom blacklist terms against listing location text and optionally relevant text fields
- reject listings that match blacklisted sub-locations

Future extension:
- add whitelist precedence if needed

### Event Rule

An event is created when:
- a matching listing appears for the first time
- an already known matching listing has a lower current price than its last known price

No other listing changes generate notifications in MVP.

## Data Model

SQLite is the system of record.

### `search_sources`

Fields:
- `id`
- `name`
- `url`
- `enabled`
- `mode`
- `publication_window_strategy`
- `location_blacklist_json`
- `location_whitelist_json`
- `created_at`
- `updated_at`

### `listings`

Fields:
- `id`
- `site_id`
- `canonical_url`
- `title`
- `location_text`
- `price_current`
- `price_first_seen`
- `price_last_notified`
- `area`
- `published_at_text`
- `contact_type`
- `content_hash`
- `first_seen_at`
- `last_seen_at`
- `last_detail_fetch_at`
- `is_active`

### `listing_evaluations`

Fields:
- `id`
- `listing_id`
- `evaluated_at`
- `is_private`
- `is_agency`
- `two_bedroom_match`
- `utilities_status`
- `location_match`
- `feature_flags_json`
- `passes_realtime`
- `passes_daily_digest`
- `reason_json`

### `price_history`

Fields:
- `id`
- `listing_id`
- `observed_at`
- `price`
- `source_run_id`

### `notifications`

Fields:
- `id`
- `listing_id`
- `channel`
- `notification_type`
- `message_hash`
- `sent_at`

Channels:
- `realtime-private`
- `daily-agency-digest`

Notification types:
- `new_listing`
- `price_drop`
- `daily_digest_entry`

### `listing_notes`

Fields:
- `id`
- `listing_id`
- `note_type`
- `note_text`
- `scheduled_for`
- `created_at`
- `created_via`

### `listing_status`

Fields:
- `listing_id`
- `status`
- `updated_at`

Initial statuses:
- `new`
- `called`
- `no_answer`
- `viewing_scheduled`
- `viewed`
- `rejected`
- `interesting`

## Deduplication and Change Detection

Primary identity:
- `site_id`

Fallback identity:
- canonicalized listing URL

Additional safeguard:
- `content_hash` over normalized title, price, area, location, and key text fields

Price drop detection:
- if current parsed price is lower than the last stored known price for the listing, create a `price_drop` event
- update `price_current`
- append a new `price_history` row

## Scheduling

Recommended MVP schedule:
- `realtime-private` polling every 5 to 10 minutes
- `daily-agency-digest` once per day
- optional once-daily wider safety sweep with a larger publication window

Publication date filters are used to reduce payload size, not as the source of truth for novelty.

## Telegram Bot Design

The Telegram bot is both the outbound notification channel and the user interaction channel.

### Notification Messages

Realtime private listing message includes:
- title
- current price
- area
- location
- private/agency marker
- `2 bedrooms: yes`
- `utilities: included_yes/partial/no/unknown`
- selected future feature flags when available
- listing URL

Price drop message includes:
- title
- old price -> new price
- location
- listing URL

Daily agency digest includes:
- short list of matching agency listings
- price and area summary per item
- listing URL per item

### Telegram Actions

The bot must support quick actions and note-taking per listing.

Supported interactions:
- mark status
- add free-text note
- schedule a viewing time
- show current status
- show note history

Example intents:
- called
- no answer
- viewing scheduled at specific time
- viewed and rejected
- interesting candidate

Implementation can use inline buttons, commands, or a hybrid approach. The key requirement is that all interaction happens inside Telegram and is usable from a phone.

## System Components

Recommended modules:
- `config`
- `fetcher`
- `parser`
- `classifier`
- `storage`
- `notifier`
- `bot`
- `runner`

Responsibilities:

`config`
- loads source URLs, polling options, Telegram settings, and rule dictionaries

`fetcher`
- requests search result pages or XHR/JSON endpoints
- requests listing detail pages

`parser`
- extracts site ids, listing cards, details, contact data, prices, location text, and publication info

`classifier`
- evaluates bedroom match, utilities status, location blacklist, and private/agency classification
- emits extensible feature flags and structured reasons

`storage`
- persists listings, evaluations, notes, prices, statuses, and notification history

`notifier`
- formats and sends outbound Telegram messages

`bot`
- receives Telegram commands/callbacks and updates notes/statuses

`runner`
- coordinates scheduled polling, event detection, digest generation, and retries

## Error Handling

MVP-grade resilience:
- short request timeouts
- small retry count
- per-source isolation so one failure does not stop other sources
- structured logs to file
- Telegram send failures are recorded and retried on the next eligible run

No complex queueing is required for MVP.

## Non-Goals and Constraints

- The service is local-first and does not require a server
- It assumes HTML/XHR formats may change and should keep parsing logic isolated
- It does not attempt high-precision geospatial filtering
- It avoids browser automation unless later required by site behavior

## Recommended Tech Stack

- Python 3.12+
- `httpx` or `requests`
- `BeautifulSoup` or `lxml`
- built-in `sqlite3`
- direct Telegram Bot API or a lightweight Telegram bot library
- Windows Task Scheduler for execution

## Implementation Roadmap

1. Inspect the site for stable XHR/JSON requests and identify search/detail parsing strategy.
2. Extract reliable fields: `site_id`, URL, publication date, title, description, price, area, location text, and `Kontaktni podatki`.
3. Build one search source and validate parsing manually.
4. Add SQLite schema and deduplication.
5. Add classifier rules for private/agency, two bedrooms, utilities, and location blacklist.
6. Add realtime Telegram notifications for private listings.
7. Add price drop detection and notifications.
8. Add daily digest for agency listings.
9. Add Telegram note and status interactions.
10. Add multiple search sources and publication-window strategies.

## Open Decisions Kept Intentional

These are intentionally deferred to implementation planning, not left ambiguous:
- exact Telegram command/button UX
- exact config file format
- whether to use a Telegram library or raw Bot API
- exact polling frequency within the recommended range

## Spec Review Notes

Self-review completed for:
- placeholder scan
- internal consistency
- scope check
- ambiguity reduction around events, agency logic, and Telegram-only interaction

Known environment limitation:
- the workspace is not currently a Git repository, so this spec cannot be committed until Git is initialized or the work is moved into a repository
