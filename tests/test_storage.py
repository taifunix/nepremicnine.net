from nepremicnine_bot.models import Listing, ListingEvaluation, ListingFeatures, ListingSnapshot
from nepremicnine_bot.storage import Database



def test_upsert_listing_and_detect_price_drop(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()

    listing = Listing(
        site_id="1111111",
        url="https://example.com/1111111",
        title="Title",
        price_current=1200,
        area=60.0,
        location_text="Center",
    )
    listing_id = db.upsert_listing(listing)
    changed = db.record_price(listing_id, 1100)

    assert listing_id == 1
    assert changed == "price_drop"



def test_get_listing_by_site_id_returns_saved_listing(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()

    listing = Listing(
        site_id="2222222",
        url="https://example.com/2222222",
        title="Saved",
        price_current=900,
        area=45.0,
        location_text="Siska",
    )
    db.upsert_listing(listing)

    loaded = db.get_listing_by_site_id("2222222")

    assert loaded is not None
    assert loaded.site_id == "2222222"
    assert loaded.price_current == 900



def test_listing_notes_and_status_are_persisted(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()

    listing_id = db.upsert_listing(
        Listing(
            site_id="3333333",
            url="https://example.com/3333333",
            title="Tracked",
            price_current=1500,
            area=70.0,
            location_text="Center",
        )
    )

    db.set_listing_status(listing_id, "called")
    db.add_listing_note(listing_id, "called", "left voicemail", None, created_via="telegram")
    db.set_listing_status(listing_id, "viewing_scheduled")
    db.add_listing_note(
        listing_id,
        "viewing_scheduled",
        "inspection booked",
        "2026-07-05T18:00",
        created_via="telegram",
    )

    status = db.get_listing_status(listing_id)
    notes = db.list_listing_notes(listing_id)

    assert status is not None
    assert status["status"] == "viewing_scheduled"
    assert len(notes) == 2
    assert notes[0]["note_type"] == "called"
    assert notes[0]["note_text"] == "left voicemail"
    assert notes[1]["note_type"] == "viewing_scheduled"
    assert notes[1]["scheduled_for"] == "2026-07-05T18:00"
    assert notes[1]["created_via"] == "telegram"



def test_snapshot_features_and_evaluation_are_persisted(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    listing_id = db.upsert_listing(
        Listing(
            site_id="4444444",
            url="https://example.com/4444444",
            title="Candidate",
            price_current=1400,
            area=64.0,
            location_text="Center",
        )
    )
    snapshot_id = db.insert_listing_snapshot(
        ListingSnapshot(
            listing_id=listing_id,
            source_url="https://example.com/4444444",
            search_title="Candidate",
            search_price_text="1.400 EUR/mesec",
            search_area_text="64 m2",
            search_location_text="Center",
            detail_title="Candidate",
            detail_description="Centralno ogrevanje. Stroški vključeni.",
            contact_block="Kontaktni podatki ZASEBNA PONUDBA",
            published_at_text="danes",
            content_hash="hash-1",
            detail_attributes_text="Št. spalnic: 2 Ogrevanje na plin",
            detail_top_tab_text="V najemnino so vključeni stroški.",
            detail_item_description="64 m2, 2,5-sobno, oddamo.",
            detail_agency_text="Kontaktni podatki ZASEBNA PONUDBA",
        )
    )
    db.upsert_listing_features(
        ListingFeatures(
            listing_id=listing_id,
            bedroom_count_guess=2,
            two_bedroom_match="yes",
            heating_text_raw="Ogrevanje na plin",
            heating_type_norm="gas",
            utilities_text_raw="Stroški vključeni",
            utilities_status="included_yes",
            location_match=True,
            reason_json={"room_count_sources": ["detail_item_description"]},
        )
    )
    db.upsert_listing_evaluation(
        ListingEvaluation(
            listing_id=listing_id,
            is_private=True,
            is_agency=False,
            two_bedroom_match="yes",
            utilities_status="included_yes",
            location_match=True,
            passes_realtime=True,
            passes_daily_digest=False,
            reason_json={"seller_source": "detail_agency_text"},
        )
    )

    snapshots = db.list_listing_snapshots(listing_id)
    features = db.get_listing_features(listing_id)
    evaluation = db.get_listing_evaluation(listing_id)

    assert snapshot_id == 1
    assert len(snapshots) == 1
    assert snapshots[0]["content_hash"] == "hash-1"
    assert snapshots[0]["detail_attributes_text"] == "Št. spalnic: 2 Ogrevanje na plin"
    assert snapshots[0]["detail_top_tab_text"] == "V najemnino so vključeni stroški."
    assert snapshots[0]["detail_item_description"] == "64 m2, 2,5-sobno, oddamo."
    assert snapshots[0]["detail_agency_text"] == "Kontaktni podatki ZASEBNA PONUDBA"
    assert features is not None
    assert features["heating_type_norm"] == "gas"
    assert features["utilities_status"] == "included_yes"
    assert evaluation is not None
    assert evaluation["is_private"] is True
    assert evaluation["passes_realtime"] is True
    assert evaluation["reason_json"]["seller_source"] == "detail_agency_text"


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
            room_count_text="2,5-sobno",
            region_text="Osrednjeslovenska",
            display_date_text="2026-07-06",
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


def test_chat_settings_are_persisted_with_defaults_and_updates(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()

    defaults = db.get_chat_settings("chat-1")
    db.upsert_chat_settings(
        "chat-1",
        {
            "price_min": 700,
            "price_max": 1200,
            "area_min": 55.0,
            "area_max": 90.0,
            "bedrooms_min": 2,
            "bedrooms_max": 3,
            "include_maybe": False,
            "seller_type": "private",
        },
    )
    updated = db.get_chat_settings("chat-1")

    assert defaults == {
        "price_min": None,
        "price_max": None,
        "area_min": None,
        "area_max": None,
        "bedrooms_min": None,
        "bedrooms_max": None,
        "include_maybe": True,
        "seller_type": "all",
    }
    assert updated == {
        "price_min": 700,
        "price_max": 1200,
        "area_min": 55.0,
        "area_max": 90.0,
        "bedrooms_min": 2,
        "bedrooms_max": 3,
        "include_maybe": False,
        "seller_type": "private",
    }


def test_chat_input_state_is_persisted_and_cleared(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()

    assert db.get_chat_input_state("chat-1") is None
    db.set_chat_input_state("chat-1", "price")
    assert db.get_chat_input_state("chat-1") == "price"
    db.clear_chat_input_state("chat-1")
    assert db.get_chat_input_state("chat-1") is None
