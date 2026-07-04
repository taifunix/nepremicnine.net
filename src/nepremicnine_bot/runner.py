def process_listing_event(existing_price: int | None, new_price: int, passes_realtime: bool) -> str | None:
    if not passes_realtime:
        return None
    if existing_price is None:
        return "new_listing"
    if new_price < existing_price:
        return "price_drop"
    return None
