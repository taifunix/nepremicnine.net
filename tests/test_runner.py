from nepremicnine_bot.classifier import classify_listing
from nepremicnine_bot.config import RuleSet, SearchSource
from nepremicnine_bot.notifier import format_realtime_message
from nepremicnine_bot.runner import poll_search_source, process_listing_event
from nepremicnine_bot.storage import Database


class StubFetcher:
    def __init__(self, payloads: dict[str, str]):
        self.payloads = payloads

    def fetch_text(self, url: str) -> str:
        return self.payloads[url]


class StubNotifier:
    def __init__(self):
        self.messages: list[str] = []

    def send_message(self, text: str) -> None:
        self.messages.append(text)



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



def test_poll_search_source_sends_new_private_listing(tmp_path):
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
              <div class='description'>V ceno so stroski vkljuceni.</div>
              <div id='kontaktni-podatki'>Kontaktni podatki ZASEBNA PONUDBA</div>
            </body></html>
            """,
        }
    )
    source = SearchSource(name="lj-center", url="https://search.example", location_blacklist=[])

    sent = poll_search_source(source, fetcher, db, notifier, RuleSet())

    assert sent == 1
    assert len(notifier.messages) == 1
    assert "Stanovanje 2 spalnici" in notifier.messages[0]



def test_cli_supports_poll_digest_and_bot_modes():
    from nepremicnine_bot.cli import build_parser

    parser = build_parser()

    assert parser.parse_args(["poll"]).command == "poll"
    assert parser.parse_args(["digest"]).command == "digest"
    assert parser.parse_args(["bot"]).command == "bot"
