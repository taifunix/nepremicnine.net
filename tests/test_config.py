import json
from pathlib import Path

from nepremicnine_bot.config import Settings
from nepremicnine_bot.models import Listing, ListingEvaluation, ListingFeatures, ListingSnapshot



def test_settings_load_sources_and_rules(tmp_path, monkeypatch):
    monkeypatch.setenv("NEPREMICNINE_BOT_TOKEN", "token")
    monkeypatch.setenv("NEPREMICNINE_CHAT_ID", "123")
    monkeypatch.setenv("NEPREMICNINE_DB_PATH", str(tmp_path / "app.db"))

    settings = Settings(
        search_sources=[
            {
                "name": "lj-center",
                "url": "https://www.nepremicnine.net/oglasi-oddaja/ljubljana/",
                "full_url": "https://www.nepremicnine.net/24ur/oglasi-oddaja/ljubljana/",
                "daily_url": "https://www.nepremicnine.net/oglasi-oddaja/ljubljana/",
                "enabled": True,
                "mode": ["realtime-private", "daily-agency-digest"],
                "publication_window_strategy": "today",
                "location_blacklist": ["bezigrad"],
            }
        ]
    )

    assert settings.telegram_bot_token == "token"
    assert settings.telegram_chat_id == "123"
    assert settings.search_sources[0].name == "lj-center"
    assert settings.search_sources[0].full_url == "https://www.nepremicnine.net/24ur/oglasi-oddaja/ljubljana/"
    assert settings.search_sources[0].daily_url == "https://www.nepremicnine.net/oglasi-oddaja/ljubljana/"
    assert "2 spalnici" in settings.rules.two_bedroom_positive



def test_settings_load_from_dotenv_file(tmp_path, monkeypatch):
    monkeypatch.delenv("NEPREMICNINE_BOT_TOKEN", raising=False)
    monkeypatch.delenv("NEPREMICNINE_CHAT_ID", raising=False)
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "BOT_TOKEN=123456:ABCdef_realistic_token\nCHAT_ID=dotenv-chat\nNEPREMICNINE_DB_PATH=./data/test.db\n",
        encoding="utf-8",
    )

    settings = Settings(_env_file=dotenv_path)

    assert settings.telegram_bot_token == "123456:ABCdef_realistic_token"
    assert settings.telegram_chat_id == "dotenv-chat"
    assert settings.db_path == "./data/test.db"



def test_settings_fallback_loads_prefixed_keys_from_raw_dotenv(tmp_path, monkeypatch):
    monkeypatch.delenv("NEPREMICNINE_BOT_TOKEN", raising=False)
    monkeypatch.delenv("NEPREMICNINE_CHAT_ID", raising=False)
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text(
        "NEPREMICNINE_BOT_TOKEN=987654:raw_fallback_token\nNEPREMICNINE_CHAT_ID=raw-chat\n",
        encoding="utf-8",
    )

    settings = Settings(_env_file=dotenv_path)

    assert settings.telegram_bot_token == "987654:raw_fallback_token"
    assert settings.telegram_chat_id == "raw-chat"



def test_settings_load_sources_from_file(tmp_path, monkeypatch):
    monkeypatch.setenv("NEPREMICNINE_BOT_TOKEN", "token")
    monkeypatch.setenv("NEPREMICNINE_CHAT_ID", "123")
    monkeypatch.setenv("NEPREMICNINE_DB_PATH", str(tmp_path / "app.db"))

    sources_file = tmp_path / "sources.json"
    sources_file.write_text(
        json.dumps(
            [
                {
                    "name": "saved-search",
                    "url": "https://www.nepremicnine.net/nepremicnine.html",
                    "full_url": "https://www.nepremicnine.net/24ur/nepremicnine.html",
                    "daily_url": "https://www.nepremicnine.net/nepremicnine.html",
                    "enabled": True,
                    "mode": ["realtime-private"],
                    "publication_window_strategy": "today",
                    "location_blacklist": ["siska"],
                }
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("NEPREMICNINE_SEARCH_SOURCES_FILE", str(sources_file))

    settings = Settings()
    sources = settings.load_search_sources()

    assert len(sources) == 1
    assert sources[0].name == "saved-search"
    assert sources[0].location_blacklist == ["siska"]
    assert sources[0].full_url == "https://www.nepremicnine.net/24ur/nepremicnine.html"
    assert sources[0].daily_url == "https://www.nepremicnine.net/nepremicnine.html"



def test_settings_load_browser_profile_options(tmp_path, monkeypatch):
    monkeypatch.setenv("NEPREMICNINE_BOT_TOKEN", "token")
    monkeypatch.setenv("NEPREMICNINE_CHAT_ID", "123")
    monkeypatch.setenv("NEPREMICNINE_DB_PATH", str(tmp_path / "app.db"))
    monkeypatch.setenv("NEPREMICNINE_BROWSER_USER_DATA_DIR", str(tmp_path / "browser-profile"))
    monkeypatch.setenv("NEPREMICNINE_BROWSER_HEADLESS", "false")
    monkeypatch.setenv("NEPREMICNINE_BROWSER_CHANNEL", "chrome")
    monkeypatch.setenv("NEPREMICNINE_BROWSER_PROXY", "user:pass@host:1234")
    monkeypatch.setenv("NEPREMICNINE_BROWSER_COOKIES_PATH", str(tmp_path / "session-cookies.json"))
    monkeypatch.setenv("NEPREMICNINE_BROWSER_STORAGE_STATE_PATH", str(tmp_path / "storage-state.json"))

    settings = Settings()

    assert settings.browser_user_data_dir.endswith("browser-profile")
    assert settings.browser_headless is False
    assert settings.browser_channel == "chrome"
    assert settings.browser_proxy == "user:pass@host:1234"
    assert settings.browser_cookies_path.endswith("session-cookies.json")
    assert settings.browser_storage_state_path.endswith("storage-state.json")



def test_listing_defaults_and_evaluation_flags():
    listing = Listing(
        site_id="123",
        url="https://example.com/123",
        title="2 spalnici",
        price_current=1200,
        area=60.0,
        location_text="Center",
    )
    evaluation = ListingEvaluation(
        listing_id=1,
        is_private=True,
        is_agency=False,
        two_bedroom_match="yes",
        utilities_status="unknown",
        location_match=True,
    )

    assert listing.is_active is True
    assert evaluation.passes_realtime is False



def test_snapshot_and_feature_models_have_expected_defaults():
    snapshot = ListingSnapshot(
        listing_id=1,
        source_url="https://www.nepremicnine.net/oglasi-oddaja/test-1111111/",
        search_title="Stanovanje 2 spalnici",
        search_price_text="1.200 EUR/mesec",
        search_area_text="60 m2",
        search_location_text="Ljubljana Center",
        detail_title="Stanovanje 2 spalnici",
        detail_description="Centralno ogrevanje. Stroški vključeni.",
        contact_block="Kontaktni podatki ZASEBNA PONUDBA",
        published_at_text="danes",
        content_hash="abc123",
    )
    features = ListingFeatures(
        listing_id=1,
        bedroom_count_guess=2,
        two_bedroom_match="yes",
        heating_text_raw="Centralno ogrevanje",
        heating_type_norm="central",
        utilities_text_raw="Stroški vključeni",
        utilities_status="included_yes",
        location_match=True,
    )

    assert snapshot.id is None
    assert features.feature_flags == {}
    assert features.reason_json == {}

