# Raw Snapshots And Text Facts Design

Date: 2026-07-06

## Goal

Extend the current MVP so that the database stores every seen listing, preserves a structured raw text snapshot for each listing, and stores separately derived text facts that can be recalculated later without revisiting the site.

This layer exists to support rule iteration on real-world data at scale: bedrooms, utilities, heating, and future features such as garden or pet-friendliness.

## Why This Slice

The current code stores only a compact listing card in `listings` and evaluates text fields only in memory during a polling run. That is too narrow for iterative rule tuning because the text that produced the decision is lost after processing.

The chosen design is `raw text snapshot + derived facts`:
- keep the compact listing record for identity and price tracking
- store normalized text snapshots from search/detail pages for every listing
- store extracted features separately from the raw text
- do not store raw HTML yet

This gives us replayability for text rules without the storage and parsing burden of full HTML archiving.

## Scope

In scope:
- save all seen listings, including those that do not pass filters
- save search/detail text snapshots for each processed listing
- save derived text facts separately from snapshots
- update the polling pipeline so notification decisions happen after persistence
- add first derived fact families for bedrooms, utilities, and heating

Out of scope for this slice:
- raw HTML storage
- geo-coordinate extraction
- agency daily digest changes
- Telegram interaction changes
- background cleanup and retention policies

## Data Model

### Existing Table Kept

`listings` remains the identity and price-tracking table.

Primary purpose:
- stable `site_id`
- canonical URL
- current price
- first-seen price
- current card-level title/location/area

### New Table: `listing_snapshots`

One row per processed capture of a listing detail page.

Fields:
- `id`
- `listing_id`
- `source_url`
- `search_title`
- `search_price_text`
- `search_area_text`
- `search_location_text`
- `detail_title`
- `detail_description`
- `contact_block`
- `published_at_text`
- `captured_at`
- `content_hash`

Purpose:
- preserve the text that was actually observed
- compare snapshots later if rules change
- enable offline extractor reruns

Notes:
- `content_hash` is built from normalized text fields, not raw HTML
- duplicate identical snapshots may be skipped later, but the first implementation may store every processed snapshot for simplicity

### New Table: `listing_features`

One row representing the latest derived text facts for a listing.

Fields:
- `listing_id`
- `bedroom_count_guess`
- `two_bedroom_match`
- `heating_text_raw`
- `heating_type_norm`
- `utilities_text_raw`
- `utilities_status`
- `location_match`
- `feature_flags_json`
- `reason_json`
- `evaluated_at`

Purpose:
- separate extracted semantics from raw text
- allow re-extraction without rewriting snapshot history
- support future rule growth without changing the snapshot schema

## Extraction Model

### Snapshot Layer

The parser produces a structured text snapshot from search card plus detail page.

Snapshot contract:
- card-level text is kept separately from detail-level text
- text is normalized only lightly: trimming, whitespace collapse, stable empty-string defaults
- no rule interpretation happens at this layer

### Derived Facts Layer

The classifier is split conceptually into two sub-steps:
1. extract text facts from the snapshot
2. compute pass/fail decisions from those facts plus configuration

Initial fact families:
- bedroom facts
  - `bedroom_count_guess`
  - `two_bedroom_match`
- utilities facts
  - `utilities_text_raw`
  - `utilities_status`
- heating facts
  - `heating_text_raw`
  - `heating_type_norm`

`feature_flags_json` remains the extensibility bucket for later facts.

## Pipeline Changes

Current flow is roughly:
- fetch search results
- fetch detail
- classify in memory
- store minimal listing row
- notify if passes

New flow becomes:
1. fetch search results
2. fetch detail page
3. build raw text snapshot
4. upsert the base listing row
5. persist a snapshot row
6. derive text facts from the snapshot
7. persist latest derived facts
8. compute notification/event decisions
9. send Telegram message only if the listing passes current filters

Consequence:
- all seen listings become analyzable later
- filtering no longer controls whether we keep the text evidence

## Module Responsibilities

### `parser.py`

Extend parser output so it can produce a stable snapshot object with both search-card and detail text fields.

### `classifier.py`

Split responsibilities into:
- text fact extraction from a snapshot
- decision calculation from facts plus rules

This is a structural improvement: bedrooms/utilities/heating become first-class extracted facts instead of only transient booleans inside one function.

### `storage.py`

Add schema and CRUD for:
- inserting/listing snapshots
- upserting latest derived facts
- reading stored snapshots later for reprocessing

### `runner.py`

Change sequencing so persistence happens before notification gating.

## Error Handling

MVP-grade behavior:
- if detail fetch fails, do not create a snapshot row for that listing in that run
- if snapshot persistence succeeds but feature extraction fails, keep the snapshot and log extraction failure separately
- notification logic uses only the latest successful derived facts

This ensures raw text is not lost just because one extractor branch fails.

## Testing Strategy

Add test coverage for:
- snapshot persistence in SQLite
- feature persistence in SQLite
- parser snapshot contract from fixtures
- extractor behavior for bedrooms/utilities/heating
- runner behavior that stores filtered-out listings without notifying them

The key regression to guard:
- a listing that does not pass realtime filtering must still appear in the database with snapshot text and derived facts

## Migration Strategy

No destructive migration is needed.

Implementation approach:
- extend `Database.initialize()` with the new tables
- preserve current `listings` rows
- start populating new tables on subsequent runs

## Review Notes

This slice is intentionally narrow:
- no raw HTML yet
- no map extraction yet
- no cleanup policy yet

Those can be added later without invalidating this model.
