import re

from nepremicnine_bot.classifier import classify_listing
from nepremicnine_bot.models import Listing
from nepremicnine_bot.notifier import format_price_drop_message, format_realtime_message
from nepremicnine_bot.parser import parse_listing_detail, parse_search_results



def _parse_price_to_int(price_text: str) -> int:
    digits = re.findall(r"\d+", price_text)
    if not digits:
        return 0
    if len(digits) == 1:
        return int(digits[0])
    return int("".join(digits[:-1]))



def _parse_area_to_float(area_text: str) -> float:
    match = re.search(r"\d+(?:[.,]\d+)?", area_text)
    if not match:
        return 0.0
    return float(match.group(0).replace(",", "."))



def process_listing_event(existing_price: int | None, new_price: int, passes_realtime: bool) -> str | None:
    if not passes_realtime:
        return None
    if existing_price is None:
        return "new_listing"
    if new_price < existing_price:
        return "price_drop"
    return None



def poll_search_source(source, fetcher, db, notifier, rules) -> int:
    sent = 0
    search_html = fetcher.fetch_text(source.url)
    results = parse_search_results(search_html)

    for result in results:
        detail_url = str(result["url"])
        detail_html = fetcher.fetch_text(detail_url)
        detail = parse_listing_detail(detail_html, detail_url)
        evaluation = classify_listing(detail, rules, source.location_blacklist)
        if not evaluation.passes_realtime:
            continue

        listing = Listing(
            site_id=str(detail["site_id"]),
            url=str(detail["url"]),
            title=str(detail["title"]),
            price_current=_parse_price_to_int(str(detail["price_text"])),
            area=_parse_area_to_float(str(detail["area_text"])),
            location_text=str(detail["location_text"]),
        )
        existing = db.get_listing_by_site_id(listing.site_id)
        listing_id = db.upsert_listing(listing)
        event = process_listing_event(
            existing_price=existing.price_current if existing else None,
            new_price=listing.price_current,
            passes_realtime=evaluation.passes_realtime,
        )
        if existing and listing.price_current != existing.price_current:
            db.record_price(listing_id, listing.price_current)
        if event == "new_listing":
            notifier.send_message(
                format_realtime_message(
                    {
                        "title": listing.title,
                        "price_current": listing.price_current,
                        "area": listing.area,
                        "location_text": listing.location_text,
                        "url": listing.url,
                    },
                    {"utilities_status": evaluation.utilities_status},
                )
            )
            sent += 1
        elif event == "price_drop" and existing is not None:
            notifier.send_message(
                format_price_drop_message(
                    {
                        "title": listing.title,
                        "price_current": listing.price_current,
                        "location_text": listing.location_text,
                        "url": listing.url,
                    },
                    existing.price_current,
                )
            )
            sent += 1

    return sent
