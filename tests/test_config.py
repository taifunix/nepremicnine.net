from nepremicnine_bot.config import Settings


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
