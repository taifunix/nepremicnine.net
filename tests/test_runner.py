from nepremicnine_bot.notifier import format_realtime_message
from nepremicnine_bot.runner import process_listing_event



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
