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
