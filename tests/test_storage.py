from nepremicnine_bot.models import Listing
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
