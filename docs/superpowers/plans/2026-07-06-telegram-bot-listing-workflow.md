# Telegram Bot Listing Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved Telegram-first listing workflow with persistent group menu, one-message-per-card rendering, inline save/reject actions, reply-based notes, DB-backed favorites/new filtering, and timed card cleanup.

**Architecture:** Extend the existing local SQLite schema so listings carry the extra summary fields and Telegram message mappings needed for UI state. Keep the bot logic in `src/nepremicnine_bot/bot.py`, keep persistence and queries in `src/nepremicnine_bot/storage.py`, and keep import/polling responsible only for writing normalized listing data plus event timestamps.

**Tech Stack:** Python 3.12, SQLite, `httpx`, Telegram Bot API, `pytest`, existing `pydantic-settings` config layer

---

## File structure

- `src/nepremicnine_bot/models.py`
  Responsibility: dataclasses for listing snapshots/features/evaluations plus any new bot-facing state fields.
- `src/nepremicnine_bot/parser.py`
  Responsibility: parse source room-count text, region text, and raw date text from imported/detail HTML.
- `src/nepremicnine_bot/storage.py`
  Responsibility: schema creation/migration, summary queries for `Новые` and `Избранное`, message mapping storage, cleanup queries.
- `src/nepremicnine_bot/runner.py`
  Responsibility: persist enriched listing data from polling/import, update price-drop event dates and rejected reset eligibility.
- `src/nepremicnine_bot/bot.py`
  Responsibility: Russian card rendering, reply keyboard, inline callback dispatch, reply-note capture, message cleanup loop.
- `src/nepremicnine_bot/cli.py`
  Responsibility: start the Telegram command loop and periodic cleanup loop from the existing `bot` entrypoint.
- `tests/test_parser.py`
  Responsibility: parser regression tests for region / room-count / date extraction.
- `tests/test_storage.py`
  Responsibility: persistence tests for summary fields, message mapping, and cleanup queries.
- `tests/test_runner.py`
  Responsibility: persistence flow tests for new normalized fields and reject-reset behavior.
- `tests/test_bot.py`
  Responsibility: menu routing, card formatting, callbacks, reply-note mapping, favorites/new filtering, cleanup behavior.

### Task 1: Enrich listing persistence with region, room count, display date, and Telegram message mapping

**Files:**
- Modify: `src/nepremicnine_bot/models.py`
- Modify: `src/nepremicnine_bot/parser.py`
- Modify: `src/nepremicnine_bot/storage.py`
- Test: `tests/test_parser.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing parser and storage tests**

```python
# tests/test_parser.py

def test_parse_listing_detail_extracts_region_room_count_and_date_fields():
    html = """
    <html><body>
      <h1>DOMŽALE, 60 m 2 - oddaja, stanovanje, 2,5-sobno</h1>
      <div id="top-tabContent">
        <div>Regija: Osrednjeslovenska</div>
      </div>
      <div class="published-at">Objavljeno: 2026-07-06</div>
    </body></html>
    """

    detail = parse_listing_detail(html, "https://www.nepremicnine.net/oglasi-oddaja/domzale-stanovanje_123/")

    assert detail["region_text"] == "Osrednjeslovenska"
    assert detail["room_count_text"] == "2,5-sobno"
    assert detail["published_at_text"] == "Objavljeno: 2026-07-06"
```

```python
# tests/test_storage.py

def test_storage_persists_summary_fields_and_message_mapping(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    listing_id = db.upsert_listing(
        Listing(
            site_id="123",
            url="https://example.com/123",
            title="Candidate",
            price_current=800,
            area=60.0,
            location_text="Domzale",
        )
    )
    db.insert_listing_snapshot(
        ListingSnapshot(
            listing_id=listing_id,
            source_url="https://example.com/123",
            search_title="Candidate",
            search_price_text="800 EUR/mesec",
            search_area_text="60 m2",
            search_location_text="Domzale",
            detail_title="DOMŽALE, 60 m 2 - oddaja, stanovanje, 2,5-sobno",
            detail_description="opis",
            contact_block="Kontaktni podatki ZASEBNA PONUDBA",
            published_at_text="Objavljeno: 2026-07-06",
            content_hash="hash-1",
            detail_top_tab_text="Regija: Osrednjeslovenska",
        )
    )
    db.upsert_listing_features(
        ListingFeatures(
            listing_id=listing_id,
            bedroom_count_guess=2,
            two_bedroom_match="yes",
            heating_text_raw="",
            heating_type_norm="unknown",
            utilities_text_raw="",
            utilities_status="unknown",
            location_match=True,
            reason_json={"room_count_text": "2,5-sobno", "region_text": "Osrednjeslovenska"},
        )
    )
    db.upsert_listing_evaluation(
        ListingEvaluation(
            listing_id=listing_id,
            is_private=True,
            is_agency=False,
            two_bedroom_match="yes",
            utilities_status="unknown",
            location_match=True,
            passes_realtime=True,
            passes_daily_digest=False,
            reason_json={"display_date_text": "2026-07-06"},
        )
    )

    db.add_telegram_message_mapping(
        chat_id="123",
        telegram_message_id=55,
        listing_id=listing_id,
        message_kind="listing_card",
        delete_after_at="2026-07-06T12:30:00",
    )

    summary = db.get_listing_summary_by_site_id("123")
    mapping = db.get_listing_by_message("123", 55)

    assert summary is not None
    assert summary["region_text"] == "Osrednjeslovenska"
    assert summary["room_count_text"] == "2,5-sobno"
    assert summary["display_date_text"] == "2026-07-06"
    assert mapping is not None
    assert mapping["listing_id"] == listing_id
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_parser.py::test_parse_listing_detail_extracts_region_room_count_and_date_fields tests/test_storage.py::test_storage_persists_summary_fields_and_message_mapping -v`
Expected: FAIL with missing keys / missing DB methods or columns.

- [ ] **Step 3: Write minimal parser, model, and storage implementation**

```python
# src/nepremicnine_bot/models.py
@dataclass(slots=True)
class ListingSnapshot:
    # existing fields...
    room_count_text: str = ""
    region_text: str = ""
    display_date_text: str = ""
```

```python
# src/nepremicnine_bot/parser.py
ROOM_COUNT_TEXT_PATTERN = re.compile(r"\b\d+(?:[.,]\d+)?-sobno\b", re.IGNORECASE)
REGION_PATTERN = re.compile(r"Regija:\s*([^|\n<]+)", re.IGNORECASE)


def _extract_room_count_text(title: str, item_description_text: str) -> str:
    for source in (title, item_description_text):
        match = ROOM_COUNT_TEXT_PATTERN.search(source)
        if match:
            return match.group(0)
    return ""


def _extract_region_text(soup: BeautifulSoup) -> str:
    text = _text_or_empty(soup.select_one("#top-tabContent"))
    match = REGION_PATTERN.search(text)
    return match.group(1).strip() if match else ""
```

```python
# src/nepremicnine_bot/storage.py
CREATE TABLE IF NOT EXISTS telegram_message_mappings (
    id INTEGER PRIMARY KEY,
    chat_id TEXT NOT NULL,
    telegram_message_id INTEGER NOT NULL,
    listing_id INTEGER NOT NULL,
    message_kind TEXT NOT NULL,
    delete_after_at TEXT NOT NULL,
    deleted_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(chat_id, telegram_message_id)
);
```

```python
# src/nepremicnine_bot/storage.py

def add_telegram_message_mapping(self, chat_id: str, telegram_message_id: int, listing_id: int, message_kind: str, delete_after_at: str) -> None:
    with self.connect() as conn:
        conn.execute(
            """
            INSERT INTO telegram_message_mappings (chat_id, telegram_message_id, listing_id, message_kind, delete_after_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, telegram_message_id) DO UPDATE SET
                listing_id = excluded.listing_id,
                message_kind = excluded.message_kind,
                delete_after_at = excluded.delete_after_at,
                deleted_at = NULL
            """,
            (chat_id, telegram_message_id, listing_id, message_kind, delete_after_at),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_parser.py::test_parse_listing_detail_extracts_region_room_count_and_date_fields tests/test_storage.py::test_storage_persists_summary_fields_and_message_mapping -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_parser.py tests/test_storage.py src/nepremicnine_bot/models.py src/nepremicnine_bot/parser.py src/nepremicnine_bot/storage.py
git commit -m "feat: persist listing summary fields and telegram message mappings"
```

### Task 2: Write Russian card formatter and listing menu reads for Новые / Избранное

**Files:**
- Modify: `src/nepremicnine_bot/storage.py`
- Modify: `src/nepremicnine_bot/bot.py`
- Test: `tests/test_bot.py`

- [ ] **Step 1: Write the failing bot tests for Russian card output and menu filters**

```python
# tests/test_bot.py

def test_render_listing_card_omits_unknowns_and_uses_russian_labels(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    listing_id = seed_listing(
        db,
        site_id="7378193",
        title="DOMŽALE, 60 m 2 - oddaja, stanovanje, 2,5-sobno",
        price_current=800,
        area=60.0,
        location_text="Domžale",
        room_count_text="2,5-sobno",
        region_text="Среднесловенский регион",
        bedroom_match="maybe",
        is_private=False,
        status="new",
    )

    card = render_listing_card(db.get_listing_summary_by_site_id("7378193"), is_saved=False)

    assert "Квартира 2,5 комнаты в Domžale" in card
    assert "Регион: Среднесловенский регион" in card
    assert "Цена: 800€" in card
    assert "Сдает агентство" in card
    assert "Площадь: 60 м²" in card
    assert "Количество комнат: 2,5" in card
    assert "Спальни: спорно" in card
    assert "unknown" not in card
    assert "Смотреть на Nepremicnine.net" in card
```

```python
# tests/test_bot.py

def test_handle_latest_and_saved_commands_apply_status_filters(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    seed_listing(db, site_id="1", title="new", status="new", passes_realtime=True)
    seed_listing(db, site_id="2", title="saved", status="saved", passes_realtime=True)
    seed_listing(db, site_id="3", title="rejected", status="rejected", passes_realtime=True)

    latest = handle_latest_command("Новые", db)
    favorites = handle_saved_command("Избранное", db)

    assert "1" in latest
    assert "2" not in latest
    assert "3" not in latest
    assert "2" in favorites
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_bot.py::test_render_listing_card_omits_unknowns_and_uses_russian_labels tests/test_bot.py::test_handle_latest_and_saved_commands_apply_status_filters -v`
Expected: FAIL with missing formatter / wrong filters / wrong labels.

- [ ] **Step 3: Write minimal formatter and menu query implementation**

```python
# src/nepremicnine_bot/bot.py

def render_listing_card(summary: dict[str, object], *, is_saved: bool) -> str:
    lines: list[str] = []
    if summary.get("display_date_text"):
        lines.append(f"Дата: {summary['display_date_text']}")
    room_count = normalize_room_count_for_ru(str(summary.get("room_count_text", "")))
    locality = str(summary.get("location_text", "")).strip()
    lines.append(f"Квартира {room_count} комнаты в {locality}")
    if is_saved:
        lines.append("⭐ ИЗБРАННОЕ")
    if summary.get("region_text"):
        lines.append(f"Регион: {summary['region_text']}")
    if summary.get("price_current"):
        lines.append(f"Цена: {summary['price_current']}€")
    if summary.get("is_private"):
        lines.append("Сдает собственник")
    elif summary.get("is_agency"):
        lines.append("Сдает агентство")
    if summary.get("area"):
        lines.append(f"Площадь: {format_area_ru(summary['area'])}")
    if room_count:
        lines.append(f"Количество комнат: {room_count}")
    lines.append(build_bedroom_line(summary))
    lines.append("Смотреть на Nepremicnine.net")
    return "\n".join(line for line in lines if line and "unknown" not in line.lower())
```

```python
# src/nepremicnine_bot/storage.py

def list_recent_listing_candidates(self, *, limit: int, mode: str) -> list[dict[str, object]]:
    where_clause = "COALESCE(ls.status, 'new') NOT IN ('saved', 'rejected')" if mode == 'new' else "COALESCE(ls.status, 'new') = 'saved'"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_bot.py::test_render_listing_card_omits_unknowns_and_uses_russian_labels tests/test_bot.py::test_handle_latest_and_saved_commands_apply_status_filters -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_bot.py src/nepremicnine_bot/storage.py src/nepremicnine_bot/bot.py
git commit -m "feat: add russian listing cards and menu filters"
```

### Task 3: Implement inline save/reject callbacks, reply-note mapping, and favorite note rendering

**Files:**
- Modify: `src/nepremicnine_bot/storage.py`
- Modify: `src/nepremicnine_bot/bot.py`
- Test: `tests/test_bot.py`

- [ ] **Step 1: Write the failing bot tests for callbacks and reply-note capture**

```python
# tests/test_bot.py

def test_save_callback_marks_listing_saved_and_edits_same_message(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    listing_id = seed_listing(db, site_id="1", title="candidate", status="new", passes_realtime=True)
    db.add_telegram_message_mapping("123", 50, listing_id, "listing_card", "2026-07-06T12:30:00")
    client = FakeTelegramClient([])

    handle_callback_query(
        {
            "message": {"chat": {"id": 123}, "message_id": 50},
            "data": "save:1",
            "id": "cb1",
        },
        client,
        db,
    )

    summary = db.get_listing_summary_by_site_id("1")
    assert summary["status"] == "saved"
    assert client.edited_messages[0][1].startswith("⭐ ИЗБРАННОЕ")
```

```python
# tests/test_bot.py

def test_reject_callback_deletes_message_and_hides_listing(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    listing_id = seed_listing(db, site_id="1", title="candidate", status="new", passes_realtime=True)
    db.add_telegram_message_mapping("123", 50, listing_id, "listing_card", "2026-07-06T12:30:00")
    client = FakeTelegramClient([])

    handle_callback_query(
        {
            "message": {"chat": {"id": 123}, "message_id": 50},
            "data": "reject:1",
            "id": "cb1",
        },
        client,
        db,
    )

    summary = db.get_listing_summary_by_site_id("1")
    latest = handle_latest_command("Новые", db)
    assert summary["status"] == "rejected"
    assert client.deleted_messages == [("123", 50)]
    assert "1" not in latest
```

```python
# tests/test_bot.py

def test_reply_to_listing_message_is_saved_as_note_and_shown_in_favorites(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    listing_id = seed_listing(db, site_id="1", title="candidate", status="saved", passes_realtime=True)
    db.add_telegram_message_mapping("123", 50, listing_id, "listing_card", "2026-07-06T12:30:00")

    save_reply_note(
        message={
            "chat": {"id": 123},
            "text": "созвонился, завтра просмотр",
            "reply_to_message": {"message_id": 50},
        },
        db=db,
    )

    favorites = handle_saved_command("Избранное", db)
    assert "созвонился, завтра просмотр" in favorites
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_bot.py::test_save_callback_marks_listing_saved_and_edits_same_message tests/test_bot.py::test_reject_callback_deletes_message_and_hides_listing tests/test_bot.py::test_reply_to_listing_message_is_saved_as_note_and_shown_in_favorites -v`
Expected: FAIL with missing callback/reply handlers.

- [ ] **Step 3: Write minimal callback and reply-note implementation**

```python
# src/nepremicnine_bot/bot.py

def handle_callback_query(callback_query: dict[str, object], client, db) -> None:
    data = str(callback_query.get("data", ""))
    chat_id = str(((callback_query.get("message") or {}).get("chat") or {}).get("id", ""))
    message_id = int(((callback_query.get("message") or {}).get("message_id", 0)))
    action, _, site_id = data.partition(":")
    summary = db.get_listing_summary_by_site_id(site_id)
    if summary is None:
        return
    if action == "save":
        db.set_listing_status(summary["listing_id"], "saved")
        refreshed = db.get_listing_summary_by_site_id(site_id)
        client.edit_message_text(chat_id, message_id, render_listing_card(refreshed, is_saved=True), reply_markup=build_card_keyboard(site_id))
    elif action == "reject":
        db.set_listing_status(summary["listing_id"], "rejected")
        db.mark_telegram_message_deleted(chat_id, message_id)
        client.delete_message(chat_id, message_id)
```

```python
# src/nepremicnine_bot/bot.py

def save_reply_note(message: dict[str, object], db) -> bool:
    reply_to = message.get("reply_to_message") or {}
    mapping = db.get_listing_by_message(str((message.get("chat") or {}).get("id", "")), int(reply_to.get("message_id", 0)))
    if mapping is None:
        return False
    db.add_listing_note(mapping["listing_id"], "note", str(message.get("text", "")).strip(), None, created_via="telegram")
    return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_bot.py::test_save_callback_marks_listing_saved_and_edits_same_message tests/test_bot.py::test_reject_callback_deletes_message_and_hides_listing tests/test_bot.py::test_reply_to_listing_message_is_saved_as_note_and_shown_in_favorites -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_bot.py src/nepremicnine_bot/storage.py src/nepremicnine_bot/bot.py
git commit -m "feat: add telegram callbacks and reply note capture"
```

### Task 4: Hook bot polling to menu texts, callback updates, TTL cleanup, and reject-reset on price drop

**Files:**
- Modify: `src/nepremicnine_bot/runner.py`
- Modify: `src/nepremicnine_bot/bot.py`
- Modify: `src/nepremicnine_bot/cli.py`
- Test: `tests/test_runner.py`
- Test: `tests/test_bot.py`

- [ ] **Step 1: Write the failing tests for price-drop reset, bot polling dispatch, and cleanup**

```python
# tests/test_runner.py

def test_price_drop_reenables_rejected_listing_for_new_menu(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    listing_id = seed_listing(db, site_id="1", title="candidate", status="rejected", passes_realtime=True, price_current=1000)
    db.record_price(listing_id, 900)

    summary = db.get_listing_summary_by_site_id("1")
    latest = handle_latest_command("Новые", db)

    assert summary["display_date_text"]
    assert "1" in latest
```

```python
# tests/test_bot.py

def test_run_command_bot_handles_menu_texts_callbacks_and_reply_notes(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    listing_id = seed_listing(db, site_id="1", title="candidate", status="new", passes_realtime=True)
    client = FakeTelegramClient(
        [[
            {"update_id": 1, "message": {"chat": {"id": 123}, "text": "Новые"}},
            {"update_id": 2, "callback_query": {"id": "cb1", "data": "save:1", "message": {"chat": {"id": 123}, "message_id": 10}}},
            {"update_id": 3, "message": {"chat": {"id": 123}, "text": "созвонился", "reply_to_message": {"message_id": 10}}},
        ]]
    )

    run_command_bot(client, "123", db, once=True, offset=0, timeout=1)

    favorites = handle_saved_command("Избранное", db)
    assert "созвонился" in favorites
```

```python
# tests/test_bot.py

def test_cleanup_expired_listing_cards_deletes_old_messages(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    listing_id = seed_listing(db, site_id="1", title="candidate", status="new", passes_realtime=True)
    db.add_telegram_message_mapping("123", 99, listing_id, "listing_card", "2000-01-01T00:00:00")
    client = FakeTelegramClient([])

    deleted = cleanup_expired_listing_cards(client, db, now_iso="2026-07-06T12:00:00")

    assert deleted == 1
    assert client.deleted_messages == [("123", 99)]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_runner.py::test_price_drop_reenables_rejected_listing_for_new_menu tests/test_bot.py::test_run_command_bot_handles_menu_texts_callbacks_and_reply_notes tests/test_bot.py::test_cleanup_expired_listing_cards_deletes_old_messages -v`
Expected: FAIL with missing reset / missing callback processing / missing cleanup.

- [ ] **Step 3: Write minimal integration implementation**

```python
# src/nepremicnine_bot/runner.py
if existing and listing.price_current != existing.price_current:
    price_event = db.record_price(existing.id or 0, listing.price_current)
    if price_event == "price_drop":
        current_status = db.get_listing_status(existing.id or 0)
        if current_status and current_status["status"] == "rejected":
            db.set_listing_status(existing.id or 0, "new")
```

```python
# src/nepremicnine_bot/bot.py

def cleanup_expired_listing_cards(client, db, *, now_iso: str | None = None) -> int:
    expired = db.list_expired_telegram_message_mappings(now_iso=now_iso)
    deleted = 0
    for item in expired:
        try:
            client.delete_message(item["chat_id"], item["telegram_message_id"])
        finally:
            db.mark_telegram_message_deleted(item["chat_id"], item["telegram_message_id"])
            deleted += 1
    return deleted
```

```python
# src/nepremicnine_bot/cli.py
elif args.command == "bot":
    settings = Settings()
    db = Database(Path(settings.db_path))
    db.initialize()
    client = TelegramBotClient(settings.telegram_bot_token)
    run_command_bot(client, settings.telegram_chat_id, db)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_runner.py::test_price_drop_reenables_rejected_listing_for_new_menu tests/test_bot.py::test_run_command_bot_handles_menu_texts_callbacks_and_reply_notes tests/test_bot.py::test_cleanup_expired_listing_cards_deletes_old_messages -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_runner.py tests/test_bot.py src/nepremicnine_bot/runner.py src/nepremicnine_bot/bot.py src/nepremicnine_bot/cli.py
git commit -m "feat: finalize telegram listing workflow"
```

## Self-review

### Spec coverage
- Persistent menu: Task 2 and Task 4
- New/Favorites filtering: Task 2
- No separate maybe menu: Task 2 formatter and filters
- Save/reject callbacks: Task 3
- Reply notes: Task 3
- Russian labels only: Task 2
- Summary title with room count + locality: Task 2
- Region field and future region readiness: Task 1 and Task 2
- Publish/price-update date in header: Task 1 and Task 4
- Auto-delete cards after 1.5 hours: Task 4
- Rejected reappears after price drop: Task 4

No spec gaps found.

### Placeholder scan
- No `TODO`, `TBD`, or “similar to task N” placeholders.
- Every task includes exact file paths, explicit tests, commands, and minimal implementation snippets.

### Type consistency
- `room_count_text`, `region_text`, `display_date_text` are used consistently across parser/storage/bot.
- Telegram mapping methods are consistently named `add_telegram_message_mapping`, `get_listing_by_message`, `mark_telegram_message_deleted`, and `list_expired_telegram_message_mappings`.
- Menu handlers are consistently named `handle_latest_command` and `handle_saved_command`.

