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
