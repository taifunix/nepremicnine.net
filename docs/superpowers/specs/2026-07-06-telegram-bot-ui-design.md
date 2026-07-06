# Telegram Bot UI Spec

Date: 2026-07-06
Status: Draft for review

## Goal

Add a Telegram-first interaction layer on top of the local Nepremicnine database so the user can:
- browse new candidates from the phone
- save or reject listings inline
- reply to a listing message to attach notes
- reopen saved listings with accumulated notes
- use a persistent menu in the group chat

This spec covers the bot UX, message format, database support for Telegram message mapping, and bot-side filtering rules. It does not include the future settings UI implementation yet.

## Scope

In scope now:
- persistent Telegram reply keyboard in the group
- separate message per listing card
- inline buttons per listing: `Сохранить`, `Не подходит`
- reply-to-message note capture for any listing status
- menu actions: `Новые`, `Избранное`, `Спорные`, `Настройки`
- card rendering from normalized DB data
- hiding rejected listings from future list outputs until a price drop occurs
- text link `Смотреть на Nepremicnine.net`

Out of scope for this step:
- settings editor flow
- bathrooms extraction
- parking spaces extraction
- multi-user permissions
- pagination beyond simple batch output

## UX Model

### Main menu

The bot publishes a persistent `ReplyKeyboardMarkup` in the group chat with four buttons:
- `Новые`
- `Избранное`
- `Спорные`
- `Настройки`

Behavior:
- `Новые` shows current realtime-private candidates that are not rejected, unless a rejected listing got a new price drop and became eligible again.
- `Избранное` shows listings explicitly saved by the user.
- `Спорные` shows `maybe` listings that need manual review.
- `Настройки` returns a placeholder message describing future settings categories.

### Per-listing message

Each listing is sent as a separate Telegram message.

Each message has inline buttons:
- `⭐ Сохранить`
- `✖ Не подходит`

Button behavior:
- `Сохранить` updates DB status to `saved` and edits the same message so the saved state is visually obvious. The leading line gets a large star marker.
- `Не подходит` updates DB status to `rejected` and edits the same message to mark it rejected. Rejected listings are excluded from future `Новые`, `Избранное`, and `Спорные` outputs until a future price drop resets visibility.

### Reply notes

Any user reply to a bot listing message is treated as a note for that listing, regardless of current status.

Examples:
- reply after `Сохранить`
- reply before any button action
- reply after `Не подходит`

The note is stored in the DB and later shown together with the listing in `Избранное` and `show`-style detail views.

## Listing card format

Only known fields are rendered. Unknown fields are omitted completely.

### Title line

The card title becomes a short summary in Russian:
- `Квартира 2,5 комнаты в Domžale`

Summary builder rules:
- prefix is always `Квартира`
- room count uses the original room count from the listing, not bedroom guess
- location uses the best short locality string available from listing data

### Body fields

Render in this order, only if present:
- `Регион: ...`
- `Цена: ...`
- `Сдает собственник`
- `Площадь: ...`
- `Количество комнат: ...`
- `Спальни: ...`

Rules:
- `Сдает собственник` is rendered only for private listings
- agency listings do not get a corresponding `Агентство` line for now
- `Количество комнат` must come from the original room count representation from the source listing, such as `2-sobno`, `2,5-sobno`, `3-sobno`
- `Спальни` comes from the classifier output when known
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
- existing ad-hoc note statuses remain allowed for note history, but UI actions use the two canonical actions above

### Visibility rules

`Новые` includes:
- listing evaluation `passes_realtime = true`
- not currently rejected
- or rejected earlier but price has dropped since rejection and a new candidate event was observed

`Избранное` includes:
- status `saved`
- not currently rejected

`Спорные` includes:
- classifier `two_bedroom_match = maybe`
- not currently rejected

`rejected` reset rule:
- when listing price drops below the previously seen price, rejection suppression is lifted for candidate output
- the old notes remain attached
- the listing may appear again in `Новые`

## Data model changes

### Telegram message mapping

Add persistence for mapping bot messages to listings. Minimum fields:
- `chat_id`
- `telegram_message_id`
- `listing_id`
- `message_kind` (`listing_card` initially)
- `created_at`

Purpose:
- map reply notes back to listing
- edit the exact card message after inline button actions
- avoid guessing which listing a reply belongs to

### Listing summary reads

DB read helpers must support:
- recent realtime candidates
- recent maybe candidates
- saved listings
- listing summary by site id
- notes for listing
- latest Telegram message mapping for listing and chat

## Bot interaction flow

### New listing flow

1. Polling/import writes listing, snapshot, features, evaluation.
2. When the bot later shows `Новые`, it queries DB and sends one message per listing.
3. After send, it stores `chat_id + telegram_message_id -> listing_id`.
4. User may press `Сохранить` or `Не подходит`.
5. Bot updates DB status and edits the same message.
6. User may reply to the message; bot stores reply text as a note.

### Saved flow

1. User opens `Избранное`.
2. Bot fetches saved listings from DB.
3. For each saved listing, bot sends the card plus accumulated notes below the card body.
4. Inline buttons remain available on the message.

### Rejected flow

1. User presses `Не подходит`.
2. Bot sets status `rejected`.
3. Bot edits the message to show rejected state.
4. Listing disappears from menu-driven lists.
5. If price later drops, normal candidate rules may surface it again.

## Future settings backlog

The `Настройки` menu is a placeholder in this step. It must later control persisted user filters for:
- bedroom count filter
- price from / to
- region whitelist or blacklist

Region filtering is explicitly part of the intended future design, so region extraction and storage are required now even though the settings UI is deferred.

## Formatting details

### Saved marker

Saved listing messages should be visually obvious. The preferred implementation is a large star marker at the top of the message, for example:
- `⭐ ИЗБРАННОЕ`

### Rejected marker

Rejected messages should be edited in place with a compact visible marker such as:
- `✖ НЕ ПОДХОДИТ`

The exact rejected marker text can be tuned during implementation, but the message must clearly show the action succeeded.

## Error handling

- replying to a non-bot message does nothing
- replying to a bot message without mapping returns a short error notice
- malformed callback data returns a short error notice and no DB change
- menu buttons with no matching listings return an explicit empty-state message
- `Настройки` returns a placeholder text rather than failing

## Testing

Required tests for the implementation:
- menu command routing for `Новые`, `Избранное`, `Спорные`, `Настройки`
- one-card-per-message formatting
- inline save action edits same message and changes DB status
- inline reject action edits same message and suppresses later list output
- reply note capture via stored message mapping
- saved listings output includes note history
- region line appears when known
- unknown fields are omitted
- room count line uses source room count, not bedroom guess
- price-drop re-surfaces previously rejected listing

## Implementation notes

Recommended implementation order:
1. extend DB for Telegram message mapping and saved-list reads
2. add room-count and region fields to summary reads and card formatter
3. implement menu rendering and text command dispatch
4. implement inline callback handling
5. implement reply-note capture by message mapping
6. implement rejected suppression with price-drop reset

## Open items intentionally deferred

- settings editor UX
- bathrooms line
- parking spaces line
- batching/pagination refinements
- richer agency/private messaging beyond `Сдает собственник`
