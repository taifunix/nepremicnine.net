import json

from nepremicnine_bot.config import Settings
from nepremicnine_bot.models import Listing, ListingEvaluation


def test_settings_load_sources_and_rules(tmp_path, monkeypatch):
    monkeypatch.setenv("NEPREMICNINE_BOT_TOKEN", "token")
    monkeypatch.setenv("NEPREMICNINE_CHAT_ID", "123")
    monkeypatch.setenv("NEPREMICNINE_DB_PATH", str(tmp_path / "app.db"))

    settings = Settings(
        search_sources=[
            {
                "name": "lj-center",
                "url": "https://www.nepremicnine.net/oglasi-oddaja/ljubljana/",
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
    assert "2 spalnici" in settings.rules.two_bedroom_positive


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
