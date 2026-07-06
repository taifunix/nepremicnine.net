# Telegram Bot UI Spec

Date: 2026-07-06
Status: Updated draft for review

## Goal

Add a Telegram-first interaction layer on top of the local Nepremicnine database so the user can:
- browse fresh listing cards from the phone
- save or reject listings inline
- reply to a listing message to attach notes
- reopen saved listings with accumulated notes
- use a persistent menu in the group chat
- keep chat noise bounded by automatic card cleanup

This spec covers the bot UX, message format, database support for Telegram message mapping, card lifecycle, and bot-side filtering rules. It does not include the future settings editor yet.

## Scope

In scope now:
- persistent Telegram reply keyboard in the group
- separate message per listing card
- inline buttons per listing: `Сохранить`, `Не подходит`
- reply-to-message note capture for any listing status
- menu actions: `Новые`, `Избранное`, `Настройки`
- card rendering from normalized DB data
- hiding rejected and saved listings from `Новые`
- showing uncertain bedroom matches directly in normal cards
- automatic deletion of listing cards from chat after 1.5 hours
- text link `Смотреть на Nepremicnine.net`
- storing listing publish/update date for card output and event handling

Out of scope for this step:
- settings editor flow
- bathrooms extraction
- parking spaces extraction
- dedicated rejected-list screen unless needed later
- multi-user permissions
- pagination beyond simple batch output

## UX Model

### Main menu

The bot publishes a persistent `ReplyKeyboardMarkup` in the group chat with three buttons:
- `Новые`
- `Избранное`
- `Настройки`

Behavior:
- `Новые` shows all current listing cards except those already rejected or saved.
- `Избранное` shows listings explicitly saved by the user earlier.
- `Настройки` returns a placeholder message describing future settings categories.

There is no separate `Спорные` menu. Uncertain listings are shown inside `Новые` as regular cards with a visible `спорно` marker in the bedroom line.

### Per-listing message

Each listing is sent as a separate Telegram message.

Each message has inline buttons:
- `⭐ Сохранить`
- `✖ Не подходит`

Button behavior:
- `Сохранить` updates DB status to `saved` and edits the same message so the saved state is visually obvious. The card gets a large star marker.
- `Не подходит` updates DB status to `rejected` and deletes the message from the chat immediately.

### Card lifetime

All listing card messages are automatically deleted from the chat after 1.5 hours.

Reason:
- avoid Telegram edit limitations on old messages
- keep the group clean
- prevent long-lived stale cards from cluttering the chat

Implications:
- reply notes are only possible while the card still exists in the chat
- saved/rejected state lives in DB and survives after message deletion
- future re-rendered cards are generated fresh from DB

### Reply notes

Any user reply to a bot listing message is treated as a note for that listing, regardless of current status.

Examples:
- reply after `Сохранить`
- reply before any button action
- reply after a fresh card appears again due to price drop

The note is stored in the DB and later shown together with the listing in `Избранное` and detail views.

## Listing card format

Only known fields are rendered. Unknown fields are omitted completely.

All card text is in Russian.

### Header block

Telegram does not support a true top-right corner. The date is therefore rendered as a compact first line in the header block.

Header structure:
1. date line
2. summary title line
3. optional saved marker

Date line rule:
- show listing publish date or last price-update date if we have one
- store this date separately in DB
- if both exist, prefer the most relevant event date being shown on the card

Examples:
- `Дата: 2026-07-06`
- `Обновление цены: 2026-07-06`

### Title line

The card title becomes a short summary in Russian:
- `Квартира 2,5 комнаты в Domžale`

Summary builder rules:
- prefix is always `Квартира`
- room count uses the original room-count representation from the source listing, not bedroom guess
- location uses the best short locality string available from listing data

### Body fields

Render in this order, only if present:
- `Регион: ...`
- `Цена: ...`
- `Сдает собственник`
- `Сдает агентство`
- `Площадь: ...`
- `Количество комнат: ...`
- `Спальни: ...`

Rules:
- private listings render `Сдает собственник`
- agency listings render `Сдает агентство`
- never render both at once
- `Количество комнат` must come from the original room count representation from the source listing, such as `2-sobno`, `2,5-sobno`, `3-sobno`, but displayed in Russian-friendly form
- `Спальни` comes from classifier output when known
- if bedroom classification is uncertain, render a Russian marker directly on that line, for example `Спальни: спорно`
- region is required in the data model because future settings will filter by region

### Footer

Instead of a raw URL, render a Telegram text link:
- `Смотреть на Nepremicnine.net`

## State model

### Listing statuses

Canonical bot-facing statuses:
- `new`
- `saved`
- `rejected`

Legacy note/status values may remain in note history, but primary UI actions use the statuses above.

### Visibility rules

`Новые` includes:
- all listings not marked `saved`
- all listings not marked `rejected`
- listings with `two_bedroom_match = yes` and `two_bedroom_match = maybe`

`Избранное` includes:
- status `saved`

`rejected` reset rule:
- when listing price drops below the previously seen price, rejection suppression is lifted
- the listing may appear again in `Новых`
- old notes remain attached

Saved reset rule:
- saved listings remain in `Избранном`
- they do not reappear in `Новых` unless explicitly unsaved in a future workflow

## Data model changes

### Telegram message mapping

Add persistence for mapping bot messages to listings. Minimum fields:
- `chat_id`
- `telegram_message_id`
- `listing_id`
- `message_kind` (`listing_card` initially)
- `created_at`
- `delete_after_at`
- `deleted_at` nullable

Purpose:
- map reply notes back to listing
- edit the exact card message after save action
- delete cards automatically after TTL
- avoid guessing which listing a reply belongs to

### Listing event date fields

Store listing date metadata separately in DB for card rendering and event logic:
- `published_at_text_raw`
- normalized event date if parseable
- `last_price_drop_at` or equivalent event timestamp
- chosen `display_date_text`

This date must be available without reparsing the site when the bot renders cards later.

### Listing summary reads

DB read helpers must support:
- recent `Новые` listings excluding saved and rejected
- saved listings
- listing summary by site id
- notes for listing
- latest Telegram message mapping for listing and chat
- expired card lookup for cleanup

## Bot interaction flow

### New listing flow

1. Polling/import writes listing, snapshot, features, evaluation.
2. User taps `Новые`.
3. Bot queries DB for listings excluding `saved` and `rejected`.
4. Bot sends one message per listing.
5. After each send, it stores `chat_id + telegram_message_id -> listing_id` with `delete_after_at = now + 90 minutes`.
6. User may press `Сохранить` or `Не подходит`.
7. User may reply to the message; bot stores reply text as a note.
8. Background cleanup deletes expired card messages.

### Save flow

1. User presses `Сохранить`.
2. Bot sets status `saved`.
3. Bot edits the same message to show saved state clearly.
4. Listing disappears from future `Новые` results.
5. Listing appears in `Избранном` together with prior notes.

### Reject flow

1. User presses `Не подходит`.
2. Bot sets status `rejected`.
3. Bot deletes the card message immediately.
4. Listing disappears from future `Новые` results.
5. If price later drops, the listing may surface again in `Новых`.

### Favorites flow

1. User taps `Избранное`.
2. Bot fetches saved listings from DB.
3. For each saved listing, bot sends the card plus accumulated notes below it.
4. Inline buttons remain available if implementation keeps them on re-rendered favorite cards.

## Future settings backlog

The `Настройки` menu is a placeholder in this step. It must later control persisted user filters for:
- bedroom count filter
- price from / to
- region filter

Region filtering is explicitly part of the intended future design, so region extraction and storage are required now even though the settings UI is deferred.

## Optional future rejected flow

A future enhancement may add a dedicated rejected-list screen with the ability to restore a listing into favorites. This is not part of the current implementation step but should not be blocked by the schema.

## Formatting details

### Saved marker

Saved listing messages should be visually obvious. Preferred leading marker:
- `⭐ ИЗБРАННОЕ`

### Rejected marker

Rejected cards are deleted immediately instead of being edited in place.

## Error handling

- replying to a non-bot message does nothing
- replying to a bot message without mapping returns a short error notice
- malformed callback data returns a short error notice and no DB change
- menu buttons with no matching listings return an explicit empty-state message
- `Настройки` returns a placeholder text rather than failing
- deleting an already deleted card should be treated as non-fatal during cleanup

## Testing

Required tests for the implementation:
- menu command routing for `Новые`, `Избранное`, `Настройки`
- one-card-per-message formatting
- save action edits same message and changes DB status
- reject action deletes message and suppresses later `Новые` output
- reply note capture via stored message mapping
- favorite listing output includes note history
- region line appears when known
- unknown fields are omitted
- room-count line uses source room count, not bedroom guess
- uncertain bedroom matches are shown in regular cards with Russian `спорно` marker
- price-drop re-surfaces previously rejected listing
- card TTL cleanup deletes old card messages
- all rendered labels are Russian

## Implementation notes

Recommended implementation order:
1. extend DB for Telegram message mapping and listing event date storage
2. add room-count and region fields to summary reads and card formatter
3. switch menu model to `Новые / Избранное / Настройки`
4. implement inline callback handling for save/reject
5. implement reply-note capture by message mapping
6. implement TTL cleanup for sent cards
7. implement rejected suppression with price-drop reset

## Open items intentionally deferred

- settings editor UX
- bathrooms line
- parking-spaces line
- dedicated rejected list UI
- batching/pagination refinements
