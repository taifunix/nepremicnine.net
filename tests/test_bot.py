from nepremicnine_bot.bot import (
    MAX_LIST_LIMIT,
    TELEGRAM_CARD_BATCH_PAUSE_SECONDS,
    TELEGRAM_RETRY_SLEEP_SECONDS,
    TelegramBotClient,
    dispatch_command,
    handle_callback_query,
    handle_expensive_command,
    handle_latest_command,
    handle_maybe_command,
    handle_note_command,
    handle_saved_command,
    handle_show_command,
    handle_status_command,
    handle_settings_command,
    parse_note_command,
    parse_status_command,
    cleanup_expired_listing_cards,
    render_listing_card,
    send_startup_menu,
    run_command_bot,
    save_reply_note,
    send_listing_cards,
)
from nepremicnine_bot.models import Listing, ListingEvaluation, ListingFeatures, ListingSnapshot
from nepremicnine_bot.storage import Database
import httpx


class FakeTelegramClient:
    def __init__(self, updates):
        self.updates = updates
        self.sent_messages: list[tuple[str, str, object | None, int]] = []
        self.edited_messages: list[tuple[str, str, str]] = []
        self.deleted_messages: list[tuple[str, int]] = []
        self.answered_callbacks: list[str] = []
        self.calls: list[tuple[int | None, int]] = []
        self.next_message_id = 10

    def get_updates(self, *, offset: int | None = None, timeout: int = 30):
        self.calls.append((offset, timeout))
        return self.updates.pop(0) if self.updates else []

    def send_message(self, chat_id: str, text: str, reply_markup=None, parse_mode=None) -> int:
        message_id = self.next_message_id
        self.next_message_id += 1
        self.sent_messages.append((chat_id, text, reply_markup, message_id))
        return message_id

    def edit_message_text(self, chat_id: str, message_id: int, text: str, reply_markup=None, parse_mode=None) -> None:
        self.edited_messages.append((chat_id, str(message_id), text))

    def delete_message(self, chat_id: str, message_id: int) -> None:
        self.deleted_messages.append((chat_id, message_id))

    def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> None:
        self.answered_callbacks.append(callback_query_id)



def _seed_listing(
    db: Database,
    *,
    site_id: str,
    title: str,
    price_current: int,
    area: float,
    location_text: str,
    two_bedroom_match: str,
    utilities_status: str,
    heating_type_norm: str,
    is_private: bool,
    passes_realtime: bool,
    status: str | None = None,
    room_count_text: str = "",
    region_text: str = "",
    display_date_text: str = "2026-07-06",
    published_at_text: str | None = None,
    captured_at: str | None = None,
    bedroom_count_guess: int | None = None,
    detail_attributes_text: str = "",
    detail_top_tab_text: str = "",
    detail_item_description: str = "",
) -> int:
    listing_id = db.upsert_listing(
        Listing(
            site_id=site_id,
            url=f"https://example.com/{site_id}",
            title=title,
            price_current=price_current,
            area=area,
            location_text=location_text,
        )
    )
    db.insert_listing_snapshot(
        ListingSnapshot(
            listing_id=listing_id,
            source_url=f"https://example.com/{site_id}",
            search_title=title,
            search_price_text=f"{price_current} EUR/mesec",
            search_area_text=f"{area} m2",
            search_location_text=location_text,
            detail_title=title,
            detail_description=title,
            contact_block="Kontaktni podatki ZASEBNA PONUDBA" if is_private else "Kontaktni podatki Agencija X",
            published_at_text=published_at_text if published_at_text is not None else display_date_text,
            content_hash=f"hash-{site_id}",
            detail_attributes_text=detail_attributes_text,
            detail_top_tab_text=detail_top_tab_text,
            detail_item_description=detail_item_description,
            room_count_text=room_count_text,
            region_text=region_text,
            display_date_text=display_date_text,
        )
    )
    if captured_at is not None:
        with db.connect() as conn:
            conn.execute(
                "UPDATE listing_snapshots SET captured_at = ? WHERE listing_id = ?",
                (captured_at, listing_id),
            )
    db.upsert_listing_features(
        ListingFeatures(
            listing_id=listing_id,
            bedroom_count_guess=bedroom_count_guess if bedroom_count_guess is not None else (2 if two_bedroom_match == "yes" else None),
            two_bedroom_match=two_bedroom_match,
            heating_text_raw=heating_type_norm,
            heating_type_norm=heating_type_norm,
            utilities_text_raw=utilities_status,
            utilities_status=utilities_status,
            location_match=True,
        )
    )
    db.upsert_listing_evaluation(
        ListingEvaluation(
            listing_id=listing_id,
            is_private=is_private,
            is_agency=not is_private,
            two_bedroom_match=two_bedroom_match,
            utilities_status=utilities_status,
            location_match=True,
            passes_realtime=passes_realtime,
            passes_daily_digest=(not is_private and two_bedroom_match == "yes"),
            reason_json={"seller_source": "detail_agency_text"},
        )
    )
    if status:
        db.set_listing_status(listing_id, status)
    return listing_id



def test_parse_note_command_with_schedule():
    command = "/note 1111111 viewing_scheduled 2026-07-05T18:00 inspection booked"

    parsed = parse_note_command(command)

    assert parsed["site_id"] == "1111111"
    assert parsed["status"] == "viewing_scheduled"
    assert parsed["scheduled_for"] == "2026-07-05T18:00"
    assert parsed["note_text"] == "inspection booked"



def test_parse_status_command():
    parsed = parse_status_command("/status 1111111 interesting")

    assert parsed == {"site_id": "1111111", "status": "interesting"}


def test_max_list_limit_is_50():
    assert MAX_LIST_LIMIT == 50



def test_render_listing_card_omits_unknowns_and_uses_russian_labels(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    _seed_listing(
        db,
        site_id="7378193",
        title="DOMŽALE, 60 m 2 - oddaja, stanovanje, 2,5-sobno",
        price_current=800,
        area=60.0,
        location_text="Domžale",
        room_count_text="2,5-sobno",
        region_text="Среднесловенский регион",
        two_bedroom_match="maybe",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=False,
        passes_realtime=False,
        status="new",
    )

    card = render_listing_card(db.get_listing_summary_by_site_id("7378193"), is_saved=False)

    assert "<b>Квартира 2,5 комнаты в Domžale</b>" in card
    assert "Регион: <b>Среднесловенский регион</b>" in card
    assert "Цена: <b>800€</b>" in card
    assert "Сдает агентство" in card
    assert "Площадь: <b>60 м²</b>" in card
    assert "Количество комнат: <b>2,5</b>" in card
    assert "Спальни: <b>спорно</b>" in card
    assert card.endswith("\n\nДата: <b>2026-07-06</b>")
    assert "unknown" not in card.lower()
    assert "Смотреть на Nepremicnine.net" in card


def test_render_listing_card_can_show_new_badge_in_header(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    _seed_listing(
        db,
        site_id="new1",
        title="DOMŽALE, 60 m 2 - oddaja, stanovanje, 2,5-sobno",
        price_current=800,
        area=60.0,
        location_text="Domžale",
        room_count_text="2,5-sobno",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=True,
        passes_realtime=True,
        status="new",
    )

    card = render_listing_card(db.get_listing_summary_by_site_id("new1"), is_saved=False, badge="НОВОЕ")

    assert card.startswith("<b>Квартира 2,5 комнаты в Domžale</b>\n\n<b>НОВОЕ</b>")
    assert "Цена: <b>800€</b>" in card
    assert card.endswith("\n\nДата: <b>2026-07-06</b>")


def test_render_listing_card_shows_previous_price_for_price_drop_and_raise(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    drop_listing_id = _seed_listing(
        db,
        site_id="pd1",
        title="DOMŽALE, 60 m 2 - oddaja, stanovanje, 2,5-sobno",
        price_current=1000,
        area=60.0,
        location_text="Domžale",
        room_count_text="2,5-sobno",
        region_text="Среднесловенский регион",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=True,
        passes_realtime=True,
        status="new",
    )
    db.record_price(drop_listing_id, 900)

    raise_listing_id = _seed_listing(
        db,
        site_id="pu1",
        title="CENTER, 55 m 2 - oddaja, stanovanje, 2-sobno",
        price_current=900,
        area=55.0,
        location_text="Center",
        room_count_text="2-sobno",
        region_text="Среднесловенский регион",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=True,
        passes_realtime=True,
        status="new",
    )
    db.record_price(raise_listing_id, 1100)

    drop_card = render_listing_card(db.get_listing_summary_by_site_id("pd1"), is_saved=False)
    raise_card = render_listing_card(db.get_listing_summary_by_site_id("pu1"), is_saved=False)

    assert "Цена: <b>900€</b> (было <b>1000€</b>)" in drop_card
    assert "Цена: <b>1100€</b> (было <b>900€</b>)" in raise_card


def test_render_listing_card_renders_utilities_status_in_russian(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    _seed_listing(
        db,
        site_id="u1",
        title="DOM?ALE, 60 m 2 - oddaja, stanovanje, 2,5-sobno",
        price_current=800,
        area=60.0,
        location_text="Dom?ale",
        room_count_text="2,5-sobno",
        region_text="???????????????? ??????",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=True,
        passes_realtime=True,
        status="new",
    )
    _seed_listing(
        db,
        site_id="u2",
        title="CENTER, 55 m 2 - oddaja, stanovanje, 2-sobno",
        price_current=900,
        area=55.0,
        location_text="Center",
        room_count_text="2-sobno",
        region_text="???????????????? ??????",
        two_bedroom_match="maybe",
        utilities_status="partial",
        heating_type_norm="gas",
        is_private=True,
        passes_realtime=True,
        status="new",
    )
    _seed_listing(
        db,
        site_id="u3",
        title="BROD, 50 m 2 - oddaja, stanovanje, 2-sobno",
        price_current=700,
        area=50.0,
        location_text="Brod",
        room_count_text="2-sobno",
        region_text="???????????????? ??????",
        two_bedroom_match="maybe",
        utilities_status="no",
        heating_type_norm="district",
        is_private=False,
        passes_realtime=False,
        status="new",
    )
    _seed_listing(
        db,
        site_id="u4",
        title="PRULE, 52 m 2 - oddaja, stanovanje, 2-sobno",
        price_current=750,
        area=52.0,
        location_text="Prule",
        room_count_text="2-sobno",
        region_text="???????????????? ??????",
        two_bedroom_match="maybe",
        utilities_status="unknown",
        heating_type_norm="district",
        is_private=False,
        passes_realtime=False,
        status="new",
    )

    included_card = render_listing_card(db.get_listing_summary_by_site_id("u1"), is_saved=False)
    partial_card = render_listing_card(db.get_listing_summary_by_site_id("u2"), is_saved=False)
    separate_card = render_listing_card(db.get_listing_summary_by_site_id("u3"), is_saved=False)
    unknown_card = render_listing_card(db.get_listing_summary_by_site_id("u4"), is_saved=False)

    assert "Коммунальные: <b>включены</b>" in included_card
    assert "Коммунальные: <b>частично включены</b>" in partial_card
    assert "Коммунальные: <b>отдельно</b>" in separate_card
    assert "Коммунальные:" not in unknown_card


def test_render_listing_card_renders_land_and_garden_line(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    _seed_listing(
        db,
        site_id="lg1",
        title="BROD - oddaja, stanovanje, 2-sobno",
        price_current=900,
        area=50.0,
        location_text="BROD",
        room_count_text="2-sobno",
        region_text="???????????????? ??????",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=True,
        passes_realtime=True,
        status="new",
        detail_attributes_text="Zemlji??e: 30,00 m 2 Vrt Atrij",
        detail_top_tab_text="Na voljo je vrt za sprostitev.",
        detail_item_description="30 m2 zemlji??a",
    )
    _seed_listing(
        db,
        site_id="lg2",
        title="ZELENA JAMA - oddaja, stanovanje, 2-sobno",
        price_current=850,
        area=54.3,
        location_text="ZELENA JAMA",
        room_count_text="2-sobno",
        region_text="???????????????? ??????",
        two_bedroom_match="maybe",
        utilities_status="no",
        heating_type_norm="district",
        is_private=False,
        passes_realtime=False,
        status="new",
        detail_attributes_text="Atrij",
        detail_top_tab_text="Stanovanje z zagrajenim atrijem.",
    )
    _seed_listing(
        db,
        site_id="lg3",
        title="BS3 - oddaja, stanovanje, 2-sobno",
        price_current=950,
        area=69.0,
        location_text="BS3",
        room_count_text="2-sobno",
        region_text="???????????????? ??????",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=True,
        passes_realtime=True,
        status="new",
        detail_attributes_text="Zemlji??e: 0,00 m 2",
        detail_top_tab_text="Bli?ina vrtca in parka.",
    )

    card_land_and_garden = render_listing_card(db.get_listing_summary_by_site_id("lg1"), is_saved=False)
    card_atrium = render_listing_card(db.get_listing_summary_by_site_id("lg2"), is_saved=False)
    card_zero = render_listing_card(db.get_listing_summary_by_site_id("lg3"), is_saved=False)

    assert "Земля/сад: <b>земля 30, сад</b>" in card_land_and_garden
    assert "Земля/сад: <b>земля</b>" in card_atrium
    assert "Земля/сад:" not in card_zero


def test_handle_latest_and_saved_commands_apply_status_filters(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    _seed_listing(
        db,
        site_id="1",
        title="New candidate",
        price_current=1000,
        area=60.0,
        location_text="Center",
        room_count_text="2,5-sobno",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=True,
        passes_realtime=True,
        status="new",
    )
    _seed_listing(
        db,
        site_id="2",
        title="Saved candidate",
        price_current=1100,
        area=62.0,
        location_text="Center",
        room_count_text="2,5-sobno",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=True,
        passes_realtime=True,
        status="saved",
    )
    _seed_listing(
        db,
        site_id="3",
        title="Rejected candidate",
        price_current=1200,
        area=65.0,
        location_text="Center",
        room_count_text="2,5-sobno",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=True,
        passes_realtime=True,
        status="rejected",
    )
    _seed_listing(
        db,
        site_id="4",
        title="Disputed candidate",
        price_current=950,
        area=55.0,
        location_text="Center",
        room_count_text="2-sobno",
        two_bedroom_match="maybe",
        utilities_status="unknown",
        heating_type_norm="district",
        is_private=True,
        passes_realtime=False,
        status="new",
    )

    latest = handle_latest_command("Новые", db)
    favorites = handle_saved_command("Избранное", db)

    assert "Цена: <b>1000€</b>" in latest
    assert "Цена: <b>1100€</b>" not in latest
    assert "Цена: <b>1200€</b>" not in latest
    assert "Цена: <b>950€</b>" in latest
    assert "Цена: <b>1100€</b>" in favorites
    assert "Цена: <b>1000€</b>" not in favorites


def test_handle_expensive_command_lists_expensive_status_only(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    _seed_listing(
        db,
        site_id="1",
        title="Expensive candidate",
        price_current=1000,
        area=60.0,
        location_text="Center",
        room_count_text="2,5-sobno",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=True,
        passes_realtime=True,
        status="expensive",
    )
    _seed_listing(
        db,
        site_id="2",
        title="New candidate",
        price_current=900,
        area=58.0,
        location_text="Center",
        room_count_text="2-sobno",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=True,
        passes_realtime=True,
        status="new",
    )

    expensive = handle_expensive_command("Дорогие", db)
    latest = handle_latest_command("Новые", db)

    assert "Цена: <b>1000€</b>" in expensive
    assert "Цена: <b>900€</b>" not in expensive
    assert "Цена: <b>1000€</b>" not in latest
    assert "Цена: <b>900€</b>" in latest



def test_save_callback_marks_listing_saved_and_edits_same_message(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    listing_id = _seed_listing(
        db,
        site_id="1",
        title="candidate",
        price_current=1000,
        area=60.0,
        location_text="Center",
        room_count_text="2,5-sobno",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=True,
        passes_realtime=True,
        status="new",
    )
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
    assert summary is not None
    assert summary["status"] == "saved"
    assert client.edited_messages[0][2].startswith("<b>Квартира 2,5 комнаты в Center</b>\n\n⭐ ИЗБРАННОЕ")
    assert client.edited_messages[0][2].endswith("\n\nДата: <b>2026-07-06</b>")



def test_reject_callback_deletes_message_and_hides_listing(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    listing_id = _seed_listing(
        db,
        site_id="1",
        title="candidate",
        price_current=1000,
        area=60.0,
        location_text="Center",
        room_count_text="2,5-sobno",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=True,
        passes_realtime=True,
        status="new",
    )
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
    assert summary is not None
    assert summary["status"] == "rejected"
    assert client.deleted_messages == [("123", 50)]
    assert "Цена: <b>1000€</b>" not in latest


def test_expensive_callback_marks_listing_expensive_and_deletes_message(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    listing_id = _seed_listing(
        db,
        site_id="1",
        title="candidate",
        price_current=1000,
        area=60.0,
        location_text="Center",
        room_count_text="2,5-sobno",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=True,
        passes_realtime=True,
        status="new",
    )
    db.add_telegram_message_mapping("123", 50, listing_id, "listing_card", "2026-07-06T12:30:00")
    client = FakeTelegramClient([])

    handle_callback_query(
        {
            "message": {"chat": {"id": 123}, "message_id": 50},
            "data": "expensive:1",
            "id": "cb1",
        },
        client,
        db,
    )

    summary = db.get_listing_summary_by_site_id("1")
    expensive = handle_expensive_command("Дорогие", db)
    latest = handle_latest_command("Новые", db)
    assert summary is not None
    assert summary["status"] == "expensive"
    assert client.deleted_messages == [("123", 50)]
    assert "Цена: <b>1000€</b>" in expensive
    assert "Цена: <b>1000€</b>" not in latest



def test_reply_to_listing_message_is_saved_as_note_and_shown_in_favorites(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    listing_id = _seed_listing(
        db,
        site_id="1",
        title="candidate",
        price_current=1000,
        area=60.0,
        location_text="Center",
        room_count_text="2,5-sobno",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=True,
        passes_realtime=True,
        status="saved",
    )
    db.add_telegram_message_mapping("123", 50, listing_id, "listing_card", "2026-07-06T12:30:00")

    saved = save_reply_note(
        message={
            "chat": {"id": 123},
            "text": "созвонился, завтра просмотр",
            "reply_to_message": {"message_id": 50},
        },
        db=db,
    )

    favorites = handle_saved_command("Избранное", db)
    assert saved is True
    assert "созвонился, завтра просмотр" in favorites



def test_handle_note_command_persists_note_and_show_returns_history(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    _seed_listing(
        db,
        site_id="1111111",
        title="Candidate",
        price_current=1300,
        area=62.0,
        location_text="Center",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=True,
        passes_realtime=True,
    )

    response = handle_note_command(
        "/note 1111111 viewing_scheduled 2026-07-05T18:00 inspection booked",
        db,
    )
    summary = handle_show_command("/show 1111111", db)

    assert "1111111" in response
    assert "viewing_scheduled" in response
    assert "inspection booked" in summary
    assert "2026-07-05T18:00" in summary
    assert "Status: viewing_scheduled" in summary
    assert "Utilities: included_yes" in summary
    assert "Heating: gas" in summary



def test_handle_status_command_updates_listing_status(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    _seed_listing(
        db,
        site_id="1111111",
        title="Candidate",
        price_current=1300,
        area=62.0,
        location_text="Center",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=True,
        passes_realtime=True,
    )

    response = handle_status_command("/status 1111111 rejected", db)
    summary = handle_show_command("/show 1111111", db)

    assert response == "Updated status for 1111111: rejected"
    assert "Status: rejected" in summary



def test_handle_latest_command_lists_realtime_candidates_only(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    _seed_listing(
        db,
        site_id="1111111",
        title="First candidate",
        price_current=1300,
        area=62.0,
        location_text="Center",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=True,
        passes_realtime=True,
    )
    _seed_listing(
        db,
        site_id="2222222",
        title="Second candidate",
        price_current=1200,
        area=58.0,
        location_text="Siska",
        two_bedroom_match="yes",
        utilities_status="no",
        heating_type_norm="district",
        is_private=True,
        passes_realtime=True,
        status="interesting",
    )
    _seed_listing(
        db,
        site_id="3333333",
        title="Filtered out",
        price_current=900,
        area=30.0,
        location_text="Siska",
        two_bedroom_match="no",
        utilities_status="unknown",
        heating_type_norm="unknown",
        is_private=True,
        passes_realtime=False,
    )

    message = handle_latest_command("/latest 2", db)

    assert "1111111" in message
    assert "2222222" in message
    assert "3333333" not in message
    assert message.index("2222222") < message.index("1111111")



def test_handle_maybe_command_lists_review_queue(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    _seed_listing(
        db,
        site_id="1111111",
        title="Maybe candidate",
        price_current=1100,
        area=55.0,
        location_text="Center",
        two_bedroom_match="maybe",
        utilities_status="no",
        heating_type_norm="district",
        is_private=True,
        passes_realtime=False,
    )
    _seed_listing(
        db,
        site_id="2222222",
        title="Sure candidate",
        price_current=1400,
        area=70.0,
        location_text="Vic",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=True,
        passes_realtime=True,
    )

    message = handle_maybe_command("/maybe", db)

    assert "Maybe queue:" in message
    assert "1111111" in message
    assert "Цена: <b>1100€</b>" in message
    assert "2222222" not in message



def test_dispatch_command_routes_to_handlers(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    _seed_listing(
        db,
        site_id="1111111",
        title="Candidate",
        price_current=1300,
        area=62.0,
        location_text="Center",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=True,
        passes_realtime=True,
    )

    assert "1111111" in dispatch_command("/latest", db)
    assert "Listing: 1111111" in dispatch_command("/show 1111111", db)
    assert "Доступно" in dispatch_command("/help", db)



def test_run_command_bot_processes_authorized_updates(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    _seed_listing(
        db,
        site_id="1111111",
        title="Candidate",
        price_current=1300,
        area=62.0,
        location_text="Center",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=True,
        passes_realtime=True,
    )
    client = FakeTelegramClient(
        [[
            {"update_id": 10, "message": {"chat": {"id": 123}, "text": "/latest 1"}},
            {"update_id": 11, "message": {"chat": {"id": 999}, "text": "/latest 1"}},
        ]]
    )

    next_offset = run_command_bot(client, "123", db, once=True, offset=0, timeout=1)

    assert next_offset == 12
    assert len(client.sent_messages) == 2
    assert client.sent_messages[0][0] == "123"
    assert "Меню доступно ниже" in client.sent_messages[0][1]
    assert client.sent_messages[0][2]["keyboard"][0][0]["text"] == "Новые"
    assert "1111111" in client.sent_messages[1][1]


def test_run_command_bot_survives_startup_send_network_error(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()

    class StartupNetworkErrorClient(FakeTelegramClient):
        def send_message(self, chat_id: str, text: str, reply_markup=None, parse_mode=None) -> int:
            request = httpx.Request("POST", "https://api.telegram.org/bot-token/sendMessage")
            raise httpx.ConnectError("network blocked", request=request)

    next_offset = run_command_bot(StartupNetworkErrorClient([[]]), "123", db, once=True, offset=5, timeout=1)

    assert next_offset == 5


def test_run_command_bot_survives_get_updates_network_error(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()

    class UpdatesNetworkErrorClient(FakeTelegramClient):
        def get_updates(self, *, offset: int | None = None, timeout: int = 30):
            request = httpx.Request("POST", "https://api.telegram.org/bot-token/getUpdates")
            raise httpx.ConnectError("network blocked", request=request)

    next_offset = run_command_bot(UpdatesNetworkErrorClient([]), "123", db, once=True, offset=7, timeout=1)

    assert next_offset == 7


def test_run_command_bot_survives_command_send_rate_limit(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()

    class CommandRateLimitedClient(FakeTelegramClient):
        def send_message(self, chat_id: str, text: str, reply_markup=None, parse_mode=None) -> int:
            if "Меню доступно ниже" in text:
                return super().send_message(chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode)
            request = httpx.Request("POST", "https://api.telegram.org/bot-token/sendMessage")
            response = httpx.Response(429, request=request)
            raise httpx.HTTPStatusError("Too Many Requests", request=request, response=response)

    next_offset = run_command_bot(
        CommandRateLimitedClient([[{"update_id": 8, "message": {"chat": {"id": 123}, "text": "Настройки"}}]]),
        "123",
        db,
        once=True,
        offset=0,
        timeout=1,
    )

    assert next_offset == 9



def test_telegram_bot_client_type_exists():
    assert TelegramBotClient is not None


def test_run_command_bot_handles_menu_texts_callbacks_and_reply_notes(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    listing_id = _seed_listing(
        db,
        site_id="1",
        title="candidate",
        price_current=1000,
        area=60.0,
        location_text="Center",
        room_count_text="2,5-sobno",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=True,
        passes_realtime=True,
        status="new",
    )
    client = FakeTelegramClient(
        [[
            {"update_id": 1, "message": {"chat": {"id": 123}, "text": "Новые"}},
            {"update_id": 2, "callback_query": {"id": "cb1", "data": "save:1", "message": {"chat": {"id": 123}, "message_id": 11}}},
            {"update_id": 3, "message": {"chat": {"id": 123}, "text": "созвонился", "reply_to_message": {"message_id": 11}}},
        ]]
    )

    run_command_bot(client, "123", db, once=True, offset=0, timeout=1)

    favorites = handle_saved_command("Избранное", db)
    mapping = db.get_listing_by_message("123", 11)
    assert len(client.sent_messages) == 2
    assert "Меню доступно ниже" in client.sent_messages[0][1]
    assert "Цена: <b>1000€</b>" in client.sent_messages[1][1]
    assert mapping is not None
    assert mapping["listing_id"] == listing_id
    assert "созвонился" in favorites


def test_run_command_bot_handles_expensive_menu_text(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    _seed_listing(
        db,
        site_id="1",
        title="expensive candidate",
        price_current=1200,
        area=60.0,
        location_text="Center",
        room_count_text="2,5-sobno",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=True,
        passes_realtime=True,
        status="expensive",
    )
    client = FakeTelegramClient([[{"update_id": 1, "message": {"chat": {"id": 123}, "text": "Дорогие"}}]])

    run_command_bot(client, "123", db, once=True, offset=0, timeout=1)

    listing_messages = [item for item in client.sent_messages if "Квартира" in item[1]]
    assert len(listing_messages) == 1
    assert "Цена: <b>1200€</b>" in listing_messages[0][1]


def test_cleanup_expired_listing_cards_deletes_old_messages(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    listing_id = _seed_listing(
        db,
        site_id="1",
        title="candidate",
        price_current=1000,
        area=60.0,
        location_text="Center",
        room_count_text="2,5-sobno",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=True,
        passes_realtime=True,
        status="new",
    )
    db.add_telegram_message_mapping("123", 99, listing_id, "listing_card", "2000-01-01T00:00:00")
    client = FakeTelegramClient([])

    deleted = cleanup_expired_listing_cards(client, db, now_iso="2026-07-06T12:00:00")

    assert deleted == 1
    assert client.deleted_messages == [("123", 99)]


def test_cleanup_expired_listing_cards_survives_telegram_delete_error(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    listing_id = _seed_listing(
        db,
        site_id="1",
        title="candidate",
        price_current=1000,
        area=60.0,
        location_text="Center",
        room_count_text="2,5-sobno",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=True,
        passes_realtime=True,
        status="new",
    )
    db.add_telegram_message_mapping("123", 99, listing_id, "listing_card", "2000-01-01T00:00:00")

    class DeleteErrorClient(FakeTelegramClient):
        def delete_message(self, chat_id: str, message_id: int) -> None:
            request = httpx.Request("POST", "https://api.telegram.org/bot-token/deleteMessage")
            response = httpx.Response(400, request=request)
            raise httpx.HTTPStatusError("Bad Request", request=request, response=response)

    deleted = cleanup_expired_listing_cards(DeleteErrorClient([]), db, now_iso="2026-07-06T12:00:00")
    expired_again = db.list_expired_telegram_message_mappings(now_iso="2026-07-06T12:00:00")

    assert deleted == 1
    assert expired_again == []


def test_send_startup_menu_publishes_persistent_keyboard():
    client = FakeTelegramClient([])

    message_id = send_startup_menu(client, "123")

    assert message_id == 10
    assert len(client.sent_messages) == 1
    assert client.sent_messages[0][0] == "123"
    assert "Меню доступно ниже" in client.sent_messages[0][1]
    assert client.sent_messages[0][2]["is_persistent"] is True
    assert client.sent_messages[0][2]["keyboard"][0][2]["text"] == "Дорогие"
    assert client.sent_messages[0][2]["keyboard"][1][0]["text"] == "Настройки"


def test_send_listing_cards_pauses_between_small_batches(tmp_path, monkeypatch):
    db = Database(tmp_path / "app.db")
    db.initialize()
    for index in range(1, 5):
        _seed_listing(
            db,
            site_id=str(index),
            title=f"candidate {index}",
            price_current=1000 + index,
            area=60.0,
            location_text="Center",
            room_count_text="2,5-sobno",
            two_bedroom_match="yes",
            utilities_status="included_yes",
            heating_type_norm="gas",
            is_private=True,
            passes_realtime=True,
            status="new",
        )
    sleep_calls: list[float] = []
    monkeypatch.setattr("nepremicnine_bot.bot.time.sleep", lambda seconds: sleep_calls.append(seconds))

    sent = send_listing_cards(
        FakeTelegramClient([]),
        "123",
        db,
        mode="new",
        now_iso="2026-07-07T08:00:00",
    )

    assert sent == 4
    assert sleep_calls == [TELEGRAM_CARD_BATCH_PAUSE_SECONDS]


def test_send_listing_cards_retries_once_after_telegram_rate_limit(tmp_path, monkeypatch):
    db = Database(tmp_path / "app.db")
    db.initialize()
    _seed_listing(
        db,
        site_id="1",
        title="candidate",
        price_current=1000,
        area=60.0,
        location_text="Center",
        room_count_text="2,5-sobno",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=True,
        passes_realtime=True,
        status="new",
    )
    sleep_calls: list[float] = []
    monkeypatch.setattr("nepremicnine_bot.bot.time.sleep", lambda seconds: sleep_calls.append(seconds))

    class RateLimitedOnceClient(FakeTelegramClient):
        def __init__(self):
            super().__init__([])
            self.failures_left = 1

        def send_message(self, chat_id: str, text: str, reply_markup=None, parse_mode=None) -> int:
            if self.failures_left:
                self.failures_left -= 1
                request = httpx.Request("POST", "https://api.telegram.org/bot-token/sendMessage")
                response = httpx.Response(429, request=request)
                raise httpx.HTTPStatusError("Too Many Requests", request=request, response=response)
            return super().send_message(chat_id, text, reply_markup=reply_markup, parse_mode=parse_mode)

    sent = send_listing_cards(
        RateLimitedOnceClient(),
        "123",
        db,
        mode="new",
        now_iso="2026-07-07T08:00:00",
    )

    assert sent == 1
    assert sleep_calls == [TELEGRAM_RETRY_SLEEP_SECONDS]


def test_send_listing_cards_stops_after_repeated_telegram_rate_limit(tmp_path, monkeypatch):
    db = Database(tmp_path / "app.db")
    db.initialize()
    _seed_listing(
        db,
        site_id="1",
        title="candidate",
        price_current=1000,
        area=60.0,
        location_text="Center",
        room_count_text="2,5-sobno",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=True,
        passes_realtime=True,
        status="new",
    )
    sleep_calls: list[float] = []
    monkeypatch.setattr("nepremicnine_bot.bot.time.sleep", lambda seconds: sleep_calls.append(seconds))

    class RateLimitedClient(FakeTelegramClient):
        def send_message(self, chat_id: str, text: str, reply_markup=None, parse_mode=None) -> int:
            request = httpx.Request("POST", "https://api.telegram.org/bot-token/sendMessage")
            response = httpx.Response(429, request=request)
            raise httpx.HTTPStatusError("Too Many Requests", request=request, response=response)

    sent = send_listing_cards(
        RateLimitedClient([]),
        "123",
        db,
        mode="new",
        now_iso="2026-07-07T08:00:00",
    )

    assert sent == 0
    assert sleep_calls == [TELEGRAM_RETRY_SLEEP_SECONDS]


def test_render_listing_card_uses_title_room_count_and_published_date_fallback(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    _seed_listing(
        db,
        site_id="55",
        title="PRULE - oddaja, stanovanje, 3-sobno",
        price_current=1250,
        area=71.0,
        location_text="PRULE",
        room_count_text="",
        display_date_text="",
        published_at_text="2026-07-06",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=True,
        passes_realtime=True,
        status="new",
    )

    card = render_listing_card(db.get_listing_summary_by_site_id("55"), is_saved=False)

    assert "<b>Квартира 3 комнаты в PRULE</b>" in card
    assert "Дата: <b>2026-07-06</b>" in card
    assert "Сдает собственник" in card


def test_handle_latest_command_renders_agency_and_date_lines(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    _seed_listing(
        db,
        site_id="88",
        title="PRULE, 65 m2 - oddaja, stanovanje, 2,5-sobno",
        price_current=1400,
        area=65.0,
        location_text="PRULE",
        room_count_text="2,5-sobno",
        region_text="Среднесловенский регион",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=False,
        passes_realtime=True,
        status="new",
    )

    latest = handle_latest_command("Новые", db)

    assert "Сдает агентство" in latest
    assert "Дата: <b>2026-07-06</b>" in latest
    assert "<b>Квартира 2,5 комнаты в PRULE</b>" in latest


def test_handle_settings_command_shows_current_chat_filters(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    db.upsert_chat_settings(
        "123",
        {
            "price_min": 700,
            "price_max": 1200,
            "area_min": 55.0,
            "area_max": 90.0,
            "bedrooms_min": 2,
            "bedrooms_max": 3,
            "include_maybe": False,
            "seller_type": "agency",
        },
    )

    text, keyboard = handle_settings_command("123", db)

    assert "Цена: 700-1200" in text
    assert "Площадь: 55-90" in text
    assert "Спальни: 2-3" in text
    assert "Показывать спорные: нет" in text
    assert "Кто сдает: агентство" in text
    assert keyboard["inline_keyboard"][0][0]["callback_data"] == "settings:price"


def test_run_command_bot_updates_settings_via_buttons_and_input(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    client = FakeTelegramClient(
        [[
            {"update_id": 1, "message": {"chat": {"id": 123}, "text": "Настройки"}},
            {"update_id": 2, "callback_query": {"id": "cb1", "data": "settings:price", "message": {"chat": {"id": 123}, "message_id": 11}}},
            {"update_id": 3, "message": {"chat": {"id": 123}, "text": "700 1200"}},
            {"update_id": 4, "callback_query": {"id": "cb2", "data": "settings:maybe:toggle", "message": {"chat": {"id": 123}, "message_id": 11}}},
            {"update_id": 5, "callback_query": {"id": "cb3", "data": "settings:seller:cycle", "message": {"chat": {"id": 123}, "message_id": 11}}},
        ]]
    )

    run_command_bot(client, "123", db, once=True, offset=0, timeout=1)

    settings = db.get_chat_settings("123")
    assert settings["price_min"] == 700
    assert settings["price_max"] == 1200
    assert settings["include_maybe"] is False
    assert settings["seller_type"] == "private"
    assert db.get_chat_input_state("123") is None
    assert any("Введите диапазон цены" in item[1] for item in client.sent_messages)


def test_run_command_bot_renders_land_and_garden_line_in_new_cards(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    _seed_listing(
        db,
        site_id="lg4",
        title="RUDNIK - oddaja, stanovanje, 2,5-sobno",
        price_current=900,
        area=60.0,
        location_text="RUDNIK",
        room_count_text="2,5-sobno",
        region_text="???????????????? ??????",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=True,
        passes_realtime=True,
        status="new",
        bedroom_count_guess=2,
        detail_attributes_text="Zemlji??e: 100,00 m 2 Vrt Atrij",
        detail_top_tab_text="Na voljo ograjena zelenica z vrtom.",
    )
    client = FakeTelegramClient([[{"update_id": 1, "message": {"chat": {"id": 123}, "text": "Новые"}}]])

    run_command_bot(client, "123", db, once=True, offset=0, timeout=1)

    listing_messages = [item for item in client.sent_messages if "Квартира" in item[1]]
    assert len(listing_messages) == 1
    assert "Земля/сад: <b>земля 100, сад</b>" in listing_messages[0][1]


def test_run_command_bot_applies_chat_filters_to_new_cards(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    _seed_listing(
        db,
        site_id="1",
        title="PRULE - oddaja, stanovanje, 2,5-sobno",
        price_current=900,
        area=60.0,
        location_text="PRULE",
        room_count_text="2,5-sobno",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=True,
        passes_realtime=True,
        status="new",
        bedroom_count_guess=2,
    )
    _seed_listing(
        db,
        site_id="2",
        title="CENTER - oddaja, stanovanje, 2,5-sobno",
        price_current=1300,
        area=60.0,
        location_text="CENTER",
        room_count_text="2,5-sobno",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=True,
        passes_realtime=True,
        status="new",
        bedroom_count_guess=2,
    )
    _seed_listing(
        db,
        site_id="3",
        title="BROD - oddaja, stanovanje, 2-sobno",
        price_current=850,
        area=52.0,
        location_text="BROD",
        room_count_text="2-sobno",
        two_bedroom_match="maybe",
        utilities_status="unknown",
        heating_type_norm="district",
        is_private=True,
        passes_realtime=False,
        status="new",
    )
    db.upsert_chat_settings(
        "123",
        {
            "price_min": 700,
            "price_max": 1200,
            "area_min": 55.0,
            "area_max": 90.0,
            "bedrooms_min": 2,
            "bedrooms_max": 2,
            "include_maybe": False,
            "seller_type": "private",
        },
    )
    client = FakeTelegramClient([[{"update_id": 1, "message": {"chat": {"id": 123}, "text": "Новые"}}]])

    run_command_bot(client, "123", db, once=True, offset=0, timeout=1)

    listing_messages = [item for item in client.sent_messages if "Квартира" in item[1]]
    assert len(listing_messages) == 1
    assert "Цена: <b>900€</b>" in listing_messages[0][1]
    assert "Цена: <b>1300€</b>" not in listing_messages[0][1]
    assert "BROD" not in listing_messages[0][1]


def test_run_command_bot_does_not_apply_chat_filters_to_saved_or_expensive_cards(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    _seed_listing(
        db,
        site_id="saved1",
        title="SAVED - oddaja, stanovanje, 1-sobno",
        price_current=1500,
        area=35.0,
        location_text="SAVED",
        room_count_text="1-sobno",
        two_bedroom_match="no",
        utilities_status="unknown",
        heating_type_norm="unknown",
        is_private=False,
        passes_realtime=False,
        status="saved",
        bedroom_count_guess=1,
    )
    _seed_listing(
        db,
        site_id="expensive1",
        title="EXPENSIVE - oddaja, stanovanje, 1-sobno",
        price_current=1600,
        area=38.0,
        location_text="EXPENSIVE",
        room_count_text="1-sobno",
        two_bedroom_match="no",
        utilities_status="unknown",
        heating_type_norm="unknown",
        is_private=False,
        passes_realtime=False,
        status="expensive",
        bedroom_count_guess=1,
    )
    db.upsert_chat_settings(
        "123",
        {
            "price_min": 700,
            "price_max": 1200,
            "area_min": 55.0,
            "area_max": 90.0,
            "bedrooms_min": 2,
            "bedrooms_max": 2,
            "include_maybe": False,
            "seller_type": "private",
        },
    )
    client = FakeTelegramClient(
        [[
            {"update_id": 1, "message": {"chat": {"id": 123}, "text": "Избранное"}},
            {"update_id": 2, "message": {"chat": {"id": 123}, "text": "Дорогие"}},
        ]]
    )

    run_command_bot(client, "123", db, once=True, offset=0, timeout=1)

    listing_messages = [item[1] for item in client.sent_messages if "Квартира" in item[1]]
    assert len(listing_messages) == 2
    assert any("SAVED" in message for message in listing_messages)
    assert any("EXPENSIVE" in message for message in listing_messages)


def test_run_command_bot_applies_seller_type_filter_to_new_cards(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    _seed_listing(
        db,
        site_id="p1",
        title="PRULE - oddaja, stanovanje, 2,5-sobno",
        price_current=900,
        area=60.0,
        location_text="PRULE",
        room_count_text="2,5-sobno",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=True,
        passes_realtime=True,
        status="new",
        bedroom_count_guess=2,
    )
    _seed_listing(
        db,
        site_id="a1",
        title="CENTER - oddaja, stanovanje, 2,5-sobno",
        price_current=950,
        area=62.0,
        location_text="CENTER",
        room_count_text="2,5-sobno",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=False,
        passes_realtime=True,
        status="new",
        bedroom_count_guess=2,
    )
    db.upsert_chat_settings("123", {"seller_type": "agency"})
    client = FakeTelegramClient([[{"update_id": 1, "message": {"chat": {"id": 123}, "text": "Новые"}}]])

    run_command_bot(client, "123", db, once=True, offset=0, timeout=1)

    listing_messages = [item for item in client.sent_messages if "Квартира" in item[1]]
    assert len(listing_messages) == 1
    assert "Сдает агентство" in listing_messages[0][1]
    assert "Сдает собственник" not in listing_messages[0][1]


def test_run_command_bot_falls_back_to_snapshot_capture_date_when_site_date_missing(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    _seed_listing(
        db,
        site_id="d1",
        title="PRULE - oddaja, stanovanje, 2,5-sobno",
        price_current=900,
        area=60.0,
        location_text="PRULE",
        room_count_text="2,5-sobno",
        display_date_text="",
        published_at_text="",
        captured_at="2026-07-06 12:34:56",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=True,
        passes_realtime=True,
        status="new",
        bedroom_count_guess=2,
    )
    client = FakeTelegramClient([[{"update_id": 1, "message": {"chat": {"id": 123}, "text": "Новые"}}]])

    run_command_bot(client, "123", db, once=True, offset=0, timeout=1)

    listing_messages = [item for item in client.sent_messages if "Квартира" in item[1]]
    assert len(listing_messages) == 1
    assert "Дата: <b>2026-07-06</b>" in listing_messages[0][1]
