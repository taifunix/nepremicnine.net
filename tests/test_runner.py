from nepremicnine_bot.notifier import format_realtime_message
import pytest
from nepremicnine_bot.runner import (
    PollSourceStats,
    audit_search_source_ids,
    import_exported_manifest,
    poll_search_source,
    poll_search_source_with_stats,
    process_listing_event,
    recover_audit_missing_results,
)


class StubFetcher:
    def __init__(self, payloads: dict[str, str]):
        self.payloads = payloads

    def fetch_text(self, url: str) -> str:
        return self.payloads[url]


class StubNotifier:
    def __init__(self):
        self.messages: list[tuple[str, str | None]] = []

    def send_message(self, text: str, parse_mode: str | None = None) -> None:
        self.messages.append((text, parse_mode))


def test_audit_search_source_ids_finds_missing_without_fetching_details(tmp_path):
    from nepremicnine_bot.config import SearchSource
    from nepremicnine_bot.models import Listing
    from nepremicnine_bot.storage import Database

    db = Database(tmp_path / "app.db")
    db.initialize()
    db.upsert_listing(
        Listing(
            site_id="1111111",
            url="https://detail.example/1111111",
            title="Known",
            price_current=1000,
            area=60.0,
            location_text="Center",
        )
    )
    fetcher = StubFetcher(
        {
            "https://search.example": """
            <html><body>
              <meta itemprop="numberOfItems" content="2">
              <div data-ad-id='1111111'><a href='https://detail.example/1111111'>Open</a></div>
              <div data-ad-id='2222222'><a href='https://detail.example/2222222'>Open</a></div>
            </body></html>
            """,
        }
    )

    stats = audit_search_source_ids(
        SearchSource(name="audit", url="https://search.example"),
        fetcher,
        db,
        watched_ids={"2222222", "3333333"},
    )

    assert stats.pages_fetched == 1
    assert stats.site_total == 2
    assert stats.parsed_unique_ids == 2
    assert stats.in_db == 1
    assert stats.missing_ids == ["2222222"]
    assert stats.watched_missing_ids == ["2222222"]
    assert stats.missing_results == [
        {
            "site_id": "2222222",
            "url": "https://detail.example/2222222",
            "title": "",
            "price_text": "",
            "area_text": "",
            "location_text": "",
        }
    ]


def test_recover_audit_missing_results_persists_missing_listing_and_notifies(tmp_path):
    from nepremicnine_bot.config import RuleSet, SearchSource
    from nepremicnine_bot.runner import SearchAuditStats
    from nepremicnine_bot.storage import Database

    db = Database(tmp_path / "app.db")
    db.initialize()
    notifier = StubNotifier()
    fetcher = StubFetcher(
        {
            "https://detail.example/2222222": """
            <html><body>
              <h1>Stanovanje 2 spalnici</h1>
              <div class='price'>1.000 EUR/mesec</div>
              <div class='area'>60 m2</div>
              <div class='location'>Center</div>
              <div class='description'>Stanovanje 2 spalnici. V ceno so stroski vkljuceni.</div>
              <div id='kontaktni-podatki'>Kontaktni podatki ZASEBNA PONUDBA</div>
              <div class='published-at'>2026-07-06</div>
            </body></html>
            """,
        }
    )
    audit = SearchAuditStats(
        source_name="audit",
        source_url="https://search.example",
        missing_ids=["2222222"],
        watched_missing_ids=[],
        missing_results=[
            {
                "site_id": "2222222",
                "url": "https://detail.example/2222222",
                "title": "Stanovanje 2 spalnici",
                "price_text": "1.000 EUR/mesec",
                "area_text": "60 m2",
                "location_text": "Center",
            }
        ],
    )
    source = SearchSource(name="audit", url="https://search.example", location_blacklist=[])

    stats = recover_audit_missing_results(source, audit, fetcher, db, notifier, RuleSet())

    assert stats.details_fetched == 1
    assert stats.new_listings == 1
    assert stats.notifications_sent == 1
    assert db.get_listing_by_site_id("2222222") is not None
    assert "<b>НОВОЕ</b>" in notifier.messages[0][0]
    assert notifier.messages[0][1] == "HTML"


def test_recover_audit_missing_results_alerts_after_three_failures(tmp_path):
    from nepremicnine_bot.config import RuleSet, SearchSource
    from nepremicnine_bot.runner import SearchAuditStats
    from nepremicnine_bot.storage import Database

    db = Database(tmp_path / "app.db")
    db.initialize()
    notifier = StubNotifier()
    fetcher = StubFetcher({})
    audit = SearchAuditStats(
        source_name="audit",
        source_url="https://search.example",
        missing_ids=["2222222"],
        watched_missing_ids=[],
        missing_results=[
            {
                "site_id": "2222222",
                "url": "https://detail.example/2222222",
                "title": "Missing",
                "price_text": "1.000 EUR/mesec",
                "area_text": "60 m2",
                "location_text": "Center",
            }
        ],
    )
    source = SearchSource(name="audit", url="https://search.example", location_blacklist=[])

    first = recover_audit_missing_results(source, audit, fetcher, db, notifier, RuleSet())
    second = recover_audit_missing_results(source, audit, fetcher, db, notifier, RuleSet())
    third = recover_audit_missing_results(source, audit, fetcher, db, notifier, RuleSet())
    fourth = recover_audit_missing_results(source, audit, fetcher, db, notifier, RuleSet())

    assert first.errors == 1
    assert second.errors == 1
    assert third.errors == 1
    assert fourth.errors == 1
    assert len(notifier.messages) == 1
    assert "AUDIT RECOVERY FAILED" in notifier.messages[0][0]
    assert "2222222" in notifier.messages[0][0]
    assert notifier.messages[0][1] is None



def test_format_realtime_message_contains_key_fields():
    listing = {
        "title": "2 spalnici",
        "price_current": 1200,
        "area": 60.0,
        "location_text": "Center",
        "url": "https://example.com",
    }
    evaluation = {"utilities_status": "included_yes"}

    message = format_realtime_message(listing, evaluation)

    assert "2 spalnici" in message
    assert "1200" in message
    assert "included_yes" in message



def test_process_listing_event_emits_new_listing():
    event = process_listing_event(existing_price=None, new_price=1200, passes_realtime=True)
    assert event == "new_listing"



def test_process_listing_event_emits_price_drop():
    event = process_listing_event(existing_price=1300, new_price=1200, passes_realtime=True)
    assert event == "price_drop"


def test_process_listing_event_emits_price_rise():
    event = process_listing_event(existing_price=1200, new_price=1300, passes_realtime=True)
    assert event == "price_rise"


def test_parse_price_to_int_handles_slovenian_thousands_format():
    from nepremicnine_bot.runner import _parse_price_to_int

    assert _parse_price_to_int("1.200 EUR/mesec") == 1200
    assert _parse_price_to_int("1.000,00 EUR/mesec") == 1000



def test_poll_search_source_sends_new_private_listing(tmp_path):
    from nepremicnine_bot.config import RuleSet, SearchSource
    from nepremicnine_bot.storage import Database

    db = Database(tmp_path / "app.db")
    db.initialize()
    notifier = StubNotifier()
    fetcher = StubFetcher(
        {
            "https://search.example": """
            <html><body>
              <div data-ad-id='1111111'>
                <a href='https://detail.example/1111111'>Open</a>
                <div class='title'>Stanovanje 2 spalnici</div>
                <div class='price'>1.200 EUR/mesec</div>
                <div class='area'>60 m2</div>
                <div class='location'>Ljubljana Center</div>
              </div>
            </body></html>
            """,
            "https://detail.example/1111111": """
            <html><body>
              <h1>Stanovanje 2 spalnici</h1>
              <div class='price'>1.200 EUR/mesec</div>
              <div class='area'>60 m2</div>
              <div class='location'>Ljubljana Center</div>
              <div class='description'>Stanovanje 2 spalnici. V ceno so stroski vkljuceni.</div>
              <div id='kontaktni-podatki'>Kontaktni podatki ZASEBNA PONUDBA</div>
            </body></html>
            """,
        }
    )
    source = SearchSource(name="lj-center", url="https://search.example", location_blacklist=[])

    sent = poll_search_source(source, fetcher, db, notifier, RuleSet())

    assert sent == 1
    assert len(notifier.messages) == 1
    assert "<b>Квартира" in notifier.messages[0][0]
    assert "<b>НОВОЕ</b>" in notifier.messages[0][0]
    assert "Цена: <b>1200€</b>" in notifier.messages[0][0]
    assert notifier.messages[0][1] == "HTML"



def test_poll_search_source_persists_filtered_out_listing_without_notifying(tmp_path):
    from nepremicnine_bot.config import RuleSet, SearchSource
    from nepremicnine_bot.storage import Database

    db = Database(tmp_path / "app.db")
    db.initialize()
    notifier = StubNotifier()
    fetcher = StubFetcher(
        {
            "https://search.example": """
            <html><body>
              <div data-ad-id='9999999'>
                <a href='https://detail.example/9999999'>Open</a>
                <div class='title'>Garsonjera</div>
                <div class='price'>900 EUR/mesec</div>
                <div class='area'>30 m2</div>
                <div class='location'>Ljubljana Siska</div>
              </div>
            </body></html>
            """,
            "https://detail.example/9999999": """
            <html><body>
              <h1>Garsonjera</h1>
              <div class='price'>900 EUR/mesec</div>
              <div class='area'>30 m2</div>
              <div class='location'>Ljubljana Siska</div>
              <div class='description'>Električno ogrevanje. Stroški niso vključeni.</div>
              <div id='kontaktni-podatki'>Kontaktni podatki ZASEBNA PONUDBA</div>
            </body></html>
            """,
        }
    )
    source = SearchSource(name="lj-center", url="https://search.example", location_blacklist=["siska"])

    sent = poll_search_source(source, fetcher, db, notifier, RuleSet())
    listing = db.get_listing_by_site_id("9999999")
    assert listing is not None
    snapshots = db.list_listing_snapshots(listing.id)
    features = db.get_listing_features(listing.id)
    evaluation = db.get_listing_evaluation(listing.id)

    assert sent == 0
    assert notifier.messages == []
    assert len(snapshots) == 1
    assert features is not None
    assert features["two_bedroom_match"] == "no"
    assert evaluation is not None
    assert evaluation["passes_realtime"] is False
    assert evaluation["is_private"] is True



def test_import_exported_manifest_persists_analysis_without_notifications(tmp_path):
    import json

    from nepremicnine_bot.config import RuleSet
    from nepremicnine_bot.storage import Database

    db = Database(tmp_path / "app.db")
    db.initialize()
    html_path = tmp_path / "7378193.html"
    html_path.write_text(
        """
        <html><body>
          <div id='agency'>
            <h4>Kontaktni podatki</h4>
            <h5>ZASEBNA PONUDBA</h5>
            <div>041 217 765</div>
          </div>
          <h1>BEŽIGRAJSKI DVOR, SAVSKI KAMEN, 63 m 2 - oddaja, stanovanje, 2-sobno</h1>
          <div class='cena'>1.000,00 EUR/mesec</div>
          <strong class='fs-15'>BEŽIGRAJSKI DVOR, SAVSKI KAMEN, 63 m2, 2-sobno, zgrajeno l. 2010, oddamo.</strong>
          <ul id='atributi'>
            <li>Velikost: 63,00 m 2</li>
            <li>Št. spalnic: 2</li>
            <li>Ogrevanje na plin</li>
          </ul>
          <div id='top-tabContent'>Stanovanje ima dve spalnici. Stroški so vključeni.</div>
        </body></html>
        """,
        encoding="utf-8",
    )
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            [
                {
                    "site_id": "7378193",
                    "url": "https://www.nepremicnine.net/oglasi-oddaja/bezigrajski-dvor-savski-kamen-stanovanje_7378193/",
                    "title": "BEŽIGRAJSKI DVOR, SAVSKI KAMEN",
                    "price_text": "1.000,00 EUR/mesec",
                    "area_text": "63,00 m 2",
                    "location_text": "BEŽIGRAJSKI DVOR, SAVSKI KAMEN",
                    "html_path": str(html_path),
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    imported = import_exported_manifest(manifest_path, db, RuleSet())
    listing = db.get_listing_by_site_id("7378193")

    assert imported == 1
    assert listing is not None
    features = db.get_listing_features(listing.id)
    evaluation = db.get_listing_evaluation(listing.id)
    snapshots = db.list_listing_snapshots(listing.id)
    assert features is not None
    assert features["two_bedroom_match"] == "yes"
    assert features["heating_type_norm"] == "gas"
    assert evaluation is not None
    assert evaluation["passes_realtime"] is True
    assert len(snapshots) == 1
    assert snapshots[0]["detail_top_tab_text"] == "Stanovanje ima dve spalnici. Stroški so vključeni."



def test_cli_supports_poll_digest_bot_warm_browser_check_session_and_import_modes():
    from nepremicnine_bot.cli import build_parser

    parser = build_parser()

    assert parser.parse_args(["poll"]).command == "poll"
    assert parser.parse_args(["poll", "--window", "daily"]).window == "daily"
    assert parser.parse_args(["audit"]).command == "audit"
    assert parser.parse_args(["audit", "--window", "daily"]).window == "daily"
    assert parser.parse_args(["digest"]).command == "digest"
    assert parser.parse_args(["bot"]).command == "bot"
    assert parser.parse_args(["warm-browser"]).command == "warm-browser"
    assert parser.parse_args(["check-session"]).command == "check-session"
    assert parser.parse_args(["import-exported", "manifest.json"]).command == "import-exported"


def test_main_poll_uses_daily_urls_when_requested(monkeypatch, tmp_path, capsys):
    import nepremicnine_bot.cli as cli
    from nepremicnine_bot.config import RuleSet, SearchSource

    class FakeSettings:
        db_path = str(tmp_path / "app.db")
        fetch_mode = "browser"
        browser_user_data_dir = str(tmp_path / "browser")
        browser_headless = False
        browser_channel = "chrome"
        browser_proxy = None
        browser_cookies_path = str(tmp_path / "session-cookies.json")
        browser_storage_state_path = str(tmp_path / "storage-state.json")
        rules = RuleSet()
        telegram_bot_token = "token"
        telegram_chat_id = "123"

        def load_search_sources(self):
            return [
                SearchSource(
                    name="s1",
                    url="https://full.example",
                    full_url="https://full.example",
                    daily_url="https://daily.example",
                )
            ]

    calls = []

    def fake_poll(source, fetcher, db, notifier, rules):
        calls.append(source.url)
        return PollSourceStats(source_name=source.name, source_url=source.url)

    monkeypatch.setattr(cli, "Settings", FakeSettings)
    monkeypatch.setattr(cli, "build_fetcher", lambda *_args, **_kwargs: "fetcher")
    monkeypatch.setattr(cli, "TelegramNotifier", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(cli, "poll_search_source_with_stats", fake_poll)

    cli.main(["poll", "--window", "daily"])

    assert calls == ["https://daily.example"]


def test_main_poll_with_audit_recover_runs_daily_audit_and_recovery(monkeypatch, tmp_path, capsys):
    import nepremicnine_bot.cli as cli
    from nepremicnine_bot.config import RuleSet, SearchSource
    from nepremicnine_bot.runner import SearchAuditStats

    class FakeSettings:
        db_path = str(tmp_path / "app.db")
        fetch_mode = "browser"
        browser_user_data_dir = str(tmp_path / "browser")
        browser_headless = False
        browser_channel = "chrome"
        browser_proxy = None
        browser_cookies_path = str(tmp_path / "session-cookies.json")
        rules = RuleSet()
        telegram_bot_token = "token"
        telegram_chat_id = "123"
        audit_watch_ids = []

        def load_search_sources(self):
            return [
                SearchSource(
                    name="s1",
                    url="https://full.example",
                    daily_url="https://daily.example",
                )
            ]

    calls = []

    def fake_poll(source, fetcher, db, notifier, rules):
        calls.append(("poll", source.url))
        return PollSourceStats(source_name=source.name, source_url=source.url)

    def fake_audit(source, fetcher, db, watched_ids):
        calls.append(("audit", source.url))
        return SearchAuditStats(source_name=source.name, source_url=source.url, missing_ids=["1"], missing_results=[])

    def fake_recover(source, audit, fetcher, db, notifier, rules):
        calls.append(("recover", source.url, audit.missing_ids))
        return PollSourceStats(source_name=f"{source.name}:audit-recovery", source_url=source.url, notifications_sent=1)

    monkeypatch.setattr(cli, "Settings", FakeSettings)
    monkeypatch.setattr(cli, "build_fetcher", lambda *_args, **_kwargs: "fetcher")
    monkeypatch.setattr(cli, "TelegramNotifier", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(cli, "poll_search_source_with_stats", fake_poll)
    monkeypatch.setattr(cli, "audit_search_source_ids", fake_audit)
    monkeypatch.setattr(cli, "recover_audit_missing_results", fake_recover)

    cli.main(["poll", "--window", "daily", "--audit-recover"])
    out = capsys.readouterr().out

    assert calls == [
        ("poll", "https://daily.example"),
        ("audit", "https://daily.example"),
        ("recover", "https://daily.example", ["1"]),
    ]
    assert "Source s1:audit-recovery:" in out
    assert "Sent 1 notifications" in out


def test_main_audit_prints_missing_and_watched_ids(monkeypatch, tmp_path, capsys):
    import nepremicnine_bot.cli as cli
    from nepremicnine_bot.config import SearchSource
    from nepremicnine_bot.runner import SearchAuditStats

    class FakeSettings:
        db_path = str(tmp_path / "app.db")
        fetch_mode = "browser"
        browser_user_data_dir = str(tmp_path / "browser")
        browser_headless = False
        browser_channel = "chrome"
        browser_proxy = None
        browser_cookies_path = str(tmp_path / "session-cookies.json")
        browser_storage_state_path = str(tmp_path / "storage-state.json")
        audit_watch_ids = ["7381374", "7381383"]

        def load_search_sources(self):
            return [SearchSource(name="s1", url="https://full.example", daily_url="https://daily.example")]

    def fake_audit(source, fetcher, db, watched_ids):
        return SearchAuditStats(
            source_name=source.name,
            source_url=source.url,
            pages_fetched=1,
            site_total=2,
            parsed_unique_ids=2,
            in_db=1,
            missing_ids=["7381374"],
            watched_missing_ids=["7381374"],
        )

    monkeypatch.setattr(cli, "Settings", FakeSettings)
    monkeypatch.setattr(cli, "build_fetcher", lambda *_args, **_kwargs: "fetcher")
    monkeypatch.setattr(cli, "audit_search_source_ids", fake_audit)

    cli.main(["audit", "--window", "daily"])
    out = capsys.readouterr().out

    assert "Audit s1:" in out
    assert "missing=1" in out
    assert "missing_ids=7381374" in out
    assert "watched_missing_ids=7381374" in out



def test_main_poll_runs_pipeline(monkeypatch, tmp_path, capsys):
    import nepremicnine_bot.cli as cli
    from nepremicnine_bot.config import RuleSet, SearchSource

    class FakeSettings:
        db_path = str(tmp_path / "app.db")
        fetch_mode = "browser"
        browser_user_data_dir = str(tmp_path / "browser")
        browser_headless = False
        browser_channel = "chrome"
        browser_proxy = "user:pass@example.com:1234"
        browser_cookies_path = str(tmp_path / "session-cookies.json")
        rules = RuleSet()
        telegram_bot_token = "token"
        telegram_chat_id = "123"

        def load_search_sources(self):
            return [SearchSource(name="s1", url="https://search.example")]

    class FakeNotifier:
        def __init__(self, *_args, **_kwargs):
            pass

    calls = []

    def fake_poll(source, fetcher, db, notifier, rules):
        calls.append((source.name, fetcher, db, notifier, rules))
        return PollSourceStats(
            source_name=source.name,
            source_url=source.url,
            search_results=5,
            details_fetched=5,
            new_listings=1,
            price_drops=1,
            price_rises=0,
            snapshots_inserted=2,
            snapshots_skipped=3,
            notifications_sent=2,
        )

    monkeypatch.setattr(cli, "Settings", FakeSettings)
    monkeypatch.setattr(
        cli,
        "build_fetcher",
        lambda mode, **kwargs: f"fetcher:{mode}:{kwargs['browser_user_data_dir']}:{kwargs['browser_channel']}:{kwargs['browser_proxy']}:{kwargs['browser_cookies_path']}",
    )
    monkeypatch.setattr(cli, "TelegramNotifier", FakeNotifier)
    monkeypatch.setattr(cli, "poll_search_source_with_stats", fake_poll)

    cli.main(["poll"])
    out = capsys.readouterr().out

    assert len(calls) == 1
    assert calls[0][0] == "s1"
    assert "Source s1:" in out
    assert "results=5" in out
    assert "details=5" in out
    assert "new=1" in out
    assert "drops=1" in out
    assert "notifications=2" in out
    assert "Total:" in out
    assert "Sent 2 notifications" in out


def test_main_poll_reports_partial_source_failure_and_exits_non_zero(monkeypatch, tmp_path, capsys):
    import nepremicnine_bot.cli as cli
    from nepremicnine_bot.config import RuleSet, SearchSource

    class FakeSettings:
        db_path = str(tmp_path / "app.db")
        fetch_mode = "browser"
        browser_user_data_dir = str(tmp_path / "browser")
        browser_headless = False
        browser_channel = "chrome"
        browser_proxy = None
        browser_cookies_path = str(tmp_path / "session-cookies.json")
        rules = RuleSet()
        telegram_bot_token = "token"
        telegram_chat_id = "123"

        def load_search_sources(self):
            return [
                SearchSource(name="ok-source", url="https://ok.example"),
                SearchSource(name="bad-source", url="https://bad.example"),
            ]

    class FakeNotifier:
        def __init__(self, *_args, **_kwargs):
            pass

    def fake_poll(source, fetcher, db, notifier, rules):
        if source.name == "bad-source":
            raise RuntimeError("search timeout")
        return PollSourceStats(
            source_name=source.name,
            source_url=source.url,
            search_results=10,
            details_fetched=8,
            new_listings=2,
            price_drops=1,
            price_rises=1,
            snapshots_inserted=4,
            snapshots_skipped=4,
            notifications_sent=3,
        )

    monkeypatch.setattr(cli, "Settings", FakeSettings)
    monkeypatch.setattr(cli, "build_fetcher", lambda mode, **kwargs: "fetcher")
    monkeypatch.setattr(cli, "TelegramNotifier", FakeNotifier)
    monkeypatch.setattr(cli, "poll_search_source_with_stats", fake_poll)

    with pytest.raises(SystemExit) as excinfo:
        cli.main(["poll"])
    out = capsys.readouterr().out

    assert excinfo.value.code == 1
    assert "Source ok-source:" in out
    assert "Source bad-source:" in out
    assert "errors=1" in out
    assert "search timeout" in out
    assert "Total:" in out



def test_main_import_exported_runs_local_pipeline(monkeypatch, tmp_path, capsys):
    import nepremicnine_bot.cli as cli
    from nepremicnine_bot.config import RuleSet

    class FakeSettings:
        db_path = str(tmp_path / "app.db")
        rules = RuleSet()

        def load_search_sources(self):
            return []

    calls = []

    def fake_import(manifest_path, db, rules):
        calls.append((str(manifest_path), db.path.name, rules))
        return 3

    monkeypatch.setattr(cli, "Settings", FakeSettings)
    monkeypatch.setattr(cli, "import_exported_manifest", fake_import)

    cli.main(["import-exported", "manifest.json"])
    out = capsys.readouterr().out

    assert calls == [("manifest.json", "app.db", FakeSettings.rules)]
    assert "Imported 3 listings" in out



def test_main_bot_runs_command_loop(monkeypatch, tmp_path, capsys):
    import nepremicnine_bot.cli as cli
    from nepremicnine_bot.config import RuleSet

    class FakeSettings:
        db_path = str(tmp_path / "app.db")
        bot_token = "token"
        chat_id = "123"
        rules = RuleSet()

        @property
        def telegram_bot_token(self):
            return self.bot_token

        @property
        def telegram_chat_id(self):
            return self.chat_id

        def load_search_sources(self):
            return []

    calls = []

    monkeypatch.setattr(cli, "Settings", FakeSettings)
    monkeypatch.setattr(cli, "TelegramBotClient", lambda token: f"client:{token}")
    monkeypatch.setattr(cli, "run_command_bot", lambda client, chat_id, db: calls.append((client, chat_id, db.path.name)))

    cli.main(["bot"])
    out = capsys.readouterr().out

    assert calls == [("client:token", "123", "app.db")]
    assert "Bot polling started" in out



def test_main_warm_browser_primes_session(monkeypatch, tmp_path, capsys):
    import nepremicnine_bot.cli as cli
    from nepremicnine_bot.config import RuleSet

    class FakeSettings:
        db_path = str(tmp_path / "app.db")
        fetch_mode = "browser"
        browser_user_data_dir = str(tmp_path / "browser")
        browser_headless = False
        browser_channel = "chrome"
        browser_proxy = "user:pass@example.com:1234"
        browser_cookies_path = str(tmp_path / "session-cookies.json")
        rules = RuleSet()
        telegram_bot_token = "token"
        telegram_chat_id = "123"

        def load_search_sources(self):
            return []

    class FakeFetcher:
        def __init__(self):
            self.warmed = []
            self.checked = []

        def warm_session(self, url: str) -> None:
            self.warmed.append(url)

        def check_session(self, url: str):
            self.checked.append(url)
            return {"ok": True, "title": "ok", "url": url}

    fake_fetcher = FakeFetcher()

    monkeypatch.setattr(cli, "Settings", FakeSettings)
    monkeypatch.setattr(cli, "build_fetcher", lambda mode, **kwargs: fake_fetcher)

    cli.main(["warm-browser", "https://www.nepremicnine.net/nepremicnine.html"])
    out = capsys.readouterr().out

    assert fake_fetcher.warmed == ["https://www.nepremicnine.net/nepremicnine.html"]
    assert "Browser session warmed" in out



def test_main_check_session_reports_result(monkeypatch, tmp_path, capsys):
    import nepremicnine_bot.cli as cli
    from nepremicnine_bot.config import RuleSet

    class FakeSettings:
        db_path = str(tmp_path / "app.db")
        fetch_mode = "browser"
        browser_user_data_dir = str(tmp_path / "browser")
        browser_headless = False
        browser_channel = "chrome"
        browser_proxy = None
        browser_cookies_path = str(tmp_path / "session-cookies.json")
        rules = RuleSet()

        def load_search_sources(self):
            return []

    class FakeFetcher:
        def __init__(self):
            self.checked = []

        def check_session(self, url: str):
            self.checked.append(url)
            return {"ok": True, "title": "Example Title", "url": url}

    fake_fetcher = FakeFetcher()

    monkeypatch.setattr(cli, "Settings", FakeSettings)
    monkeypatch.setattr(cli, "build_fetcher", lambda mode, **kwargs: fake_fetcher)

    cli.main(["check-session", "https://www.nepremicnine.net/nepremicnine.html"])
    out = capsys.readouterr().out

    assert fake_fetcher.checked == ["https://www.nepremicnine.net/nepremicnine.html"]
    assert "Session OK" in out
    assert "Example Title" in out



def test_safe_console_text_escapes_unencodable_console_characters():
    import nepremicnine_bot.cli as cli

    assert cli._safe_console_text("Nepremičnine", "cp1251") == "Nepremi\\u010dnine"


def test_price_drop_reenables_rejected_listing_for_new_menu(tmp_path):
    from nepremicnine_bot.bot import handle_latest_command
    from nepremicnine_bot.config import RuleSet, SearchSource
    from nepremicnine_bot.storage import Database
    from tests.test_bot import _seed_listing

    db = Database(tmp_path / "app.db")
    db.initialize()
    _seed_listing(
        db,
        site_id="1",
        title="Candidate",
        price_current=1000,
        area=60.0,
        location_text="Center",
        room_count_text="2,5-sobno",
        two_bedroom_match="yes",
        utilities_status="included_yes",
        heating_type_norm="gas",
        is_private=True,
        passes_realtime=True,
        status="rejected",
    )

    notifier = StubNotifier()
    fetcher = StubFetcher(
        {
            "https://search.example": """
            <html><body>
              <div data-ad-id='1'>
                <a href='https://detail.example/1'>Open</a>
                <div class='title'>Stanovanje 2 spalnici</div>
                <div class='price'>900 EUR/mesec</div>
                <div class='area'>60 m2</div>
                <div class='location'>Center</div>
              </div>
            </body></html>
            """,
            "https://detail.example/1": """
            <html><body>
              <h1>Stanovanje 2 spalnici</h1>
              <div class='price'>900 EUR/mesec</div>
              <div class='area'>60 m2</div>
              <div class='location'>Center</div>
              <div class='description'>Stanovanje 2 spalnici. V ceno so stroski vkljuceni.</div>
              <div id='kontaktni-podatki'>Kontaktni podatki ZASEBNA PONUDBA</div>
              <div class='published-at'>2026-07-06</div>
            </body></html>
            """,
        }
    )
    source = SearchSource(name="lj-center", url="https://search.example", location_blacklist=[])

    sent = poll_search_source(source, fetcher, db, notifier, RuleSet())

    summary = db.get_listing_summary_by_site_id("1")
    latest = handle_latest_command("Новые", db)
    assert sent == 1
    assert summary is not None
    assert summary["status"] == "new"
    assert summary["display_date_text"] == "2026-07-06"
    assert "Цена: <b>900€</b>" in latest


def test_price_rise_sends_card_with_previous_price(tmp_path):
    from nepremicnine_bot.config import RuleSet, SearchSource
    from nepremicnine_bot.storage import Database
    from tests.test_bot import _seed_listing

    db = Database(tmp_path / "app.db")
    db.initialize()
    _seed_listing(
        db,
        site_id="1",
        title="Candidate",
        price_current=900,
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
    notifier = StubNotifier()
    fetcher = StubFetcher(
        {
            "https://search.example": """
            <html><body>
              <div data-ad-id='1'>
                <a href='https://detail.example/1'>Open</a>
                <div class='title'>Stanovanje 2 spalnici</div>
                <div class='price'>1.100 EUR/mesec</div>
                <div class='area'>60 m2</div>
                <div class='location'>Center</div>
              </div>
            </body></html>
            """,
            "https://detail.example/1": """
            <html><body>
              <h1>Stanovanje 2 spalnici</h1>
              <div class='price'>1.100 EUR/mesec</div>
              <div class='area'>60 m2</div>
              <div class='location'>Center</div>
              <div class='description'>Stanovanje 2 spalnici. V ceno so stroski vkljuceni.</div>
              <div id='kontaktni-podatki'>Kontaktni podatki ZASEBNA PONUDBA</div>
              <div class='published-at'>2026-07-06</div>
            </body></html>
            """,
        }
    )
    source = SearchSource(name="lj-center", url="https://search.example", location_blacklist=[])

    sent = poll_search_source(source, fetcher, db, notifier, RuleSet())

    assert sent == 1
    assert "ЦЕНА ИЗМЕНИЛАСЬ" in notifier.messages[0][0]
    assert "Цена: <b>1100€</b> (было <b>900€</b>)" in notifier.messages[0][0]
    assert notifier.messages[0][1] == "HTML"


def test_poll_search_source_skips_duplicate_snapshot_when_content_is_unchanged(tmp_path):
    from nepremicnine_bot.config import RuleSet, SearchSource
    from nepremicnine_bot.storage import Database

    db = Database(tmp_path / "app.db")
    db.initialize()
    notifier = StubNotifier()
    fetcher = StubFetcher(
        {
            "https://search.example": """
            <html><body>
              <div data-ad-id='1111111'>
                <a href='https://detail.example/1111111'>Open</a>
                <div class='title'>Stanovanje 2 spalnici</div>
                <div class='price'>1.200 EUR/mesec</div>
                <div class='area'>60 m2</div>
                <div class='location'>Ljubljana Center</div>
              </div>
            </body></html>
            """,
            "https://detail.example/1111111": """
            <html><body>
              <h1>Stanovanje 2 spalnici</h1>
              <div class='price'>1.200 EUR/mesec</div>
              <div class='area'>60 m2</div>
              <div class='location'>Ljubljana Center</div>
              <div class='description'>Stanovanje 2 spalnici. V ceno so stroski vkljuceni.</div>
              <div id='kontaktni-podatki'>Kontaktni podatki ZASEBNA PONUDBA</div>
            </body></html>
            """,
        }
    )
    source = SearchSource(name="lj-center", url="https://search.example", location_blacklist=[])

    first_sent = poll_search_source(source, fetcher, db, notifier, RuleSet())
    second_sent = poll_search_source(source, fetcher, db, notifier, RuleSet())

    listing = db.get_listing_by_site_id("1111111")
    assert listing is not None
    snapshots = db.list_listing_snapshots(listing.id)

    assert first_sent == 1
    assert second_sent == 0
    assert len(snapshots) == 1


def test_poll_search_source_walks_all_paginated_pages_with_fallback(tmp_path):
    from nepremicnine_bot.config import RuleSet, SearchSource
    from nepremicnine_bot.storage import Database

    db = Database(tmp_path / "app.db")
    db.initialize()
    notifier = StubNotifier()
    fetcher = StubFetcher(
        {
            "https://search.example": """
            <html><body>
              <meta itemprop="numberOfItems" content="4">
              <div data-ad-id='1111111'>
                <a href='https://detail.example/1111111'>Open</a>
                <div class='title'>One</div>
                <div class='price'>1.000 EUR/mesec</div>
                <div class='area'>60 m2</div>
                <div class='location'>Center</div>
              </div>
              <div data-ad-id='2222222'>
                <a href='https://detail.example/2222222'>Open</a>
                <div class='title'>Two</div>
                <div class='price'>1.100 EUR/mesec</div>
                <div class='area'>61 m2</div>
                <div class='location'>Center</div>
              </div>
            </body></html>
            """,
            "https://search.example?stran=2": """
            <html><body>
              <meta itemprop="numberOfItems" content="4">
              <div data-ad-id='3333333'>
                <a href='https://detail.example/3333333'>Open</a>
                <div class='title'>Three</div>
                <div class='price'>1.200 EUR/mesec</div>
                <div class='area'>62 m2</div>
                <div class='location'>Center</div>
              </div>
              <div data-ad-id='4444444'>
                <a href='https://detail.example/4444444'>Open</a>
                <div class='title'>Four</div>
                <div class='price'>1.300 EUR/mesec</div>
                <div class='area'>63 m2</div>
                <div class='location'>Center</div>
              </div>
            </body></html>
            """,
            "https://detail.example/1111111": """
            <html><body><h1>One 2 spalnici</h1><div class='price'>1.000 EUR/mesec</div><div class='area'>60 m2</div><div class='location'>Center</div><div class='description'>2 spalnici. stroski vkljuceni.</div><div id='kontaktni-podatki'>Kontaktni podatki ZASEBNA PONUDBA</div></body></html>
            """,
            "https://detail.example/2222222": """
            <html><body><h1>Two 2 spalnici</h1><div class='price'>1.100 EUR/mesec</div><div class='area'>61 m2</div><div class='location'>Center</div><div class='description'>2 spalnici. stroski vkljuceni.</div><div id='kontaktni-podatki'>Kontaktni podatki ZASEBNA PONUDBA</div></body></html>
            """,
            "https://detail.example/3333333": """
            <html><body><h1>Three 2 spalnici</h1><div class='price'>1.200 EUR/mesec</div><div class='area'>62 m2</div><div class='location'>Center</div><div class='description'>2 spalnici. stroski vkljuceni.</div><div id='kontaktni-podatki'>Kontaktni podatki ZASEBNA PONUDBA</div></body></html>
            """,
            "https://detail.example/4444444": """
            <html><body><h1>Four 2 spalnici</h1><div class='price'>1.300 EUR/mesec</div><div class='area'>63 m2</div><div class='location'>Center</div><div class='description'>2 spalnici. stroski vkljuceni.</div><div id='kontaktni-podatki'>Kontaktni podatki ZASEBNA PONUDBA</div></body></html>
            """,
        }
    )
    source = SearchSource(name="paginated", url="https://search.example", location_blacklist=[])

    stats = poll_search_source_with_stats(source, fetcher, db, notifier, RuleSet())

    assert stats.pages_fetched == 2
    assert stats.search_results == 4
    assert stats.details_fetched == 4
    assert stats.notifications_sent == 4
    assert db.get_listing_by_site_id("4444444") is not None
