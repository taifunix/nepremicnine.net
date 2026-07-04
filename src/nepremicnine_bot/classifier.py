from nepremicnine_bot.models import ListingEvaluation



def classify_listing(detail: dict[str, object], rules, location_blacklist: list[str]) -> ListingEvaluation:
    haystack = " ".join(
        str(detail.get(key, "")).lower()
        for key in ("title", "description", "contact_block", "location_text")
    )
    location_text = str(detail.get("location_text", "")).lower()
    contact_block = str(detail.get("contact_block", ""))

    is_private = "ZASEBNA PONUDBA" in contact_block
    is_agency = not is_private

    if any(term.lower() in haystack for term in rules.two_bedroom_positive):
        bedroom_match = "yes"
    elif any(term.lower() in haystack for term in rules.two_bedroom_negative):
        bedroom_match = "no"
    else:
        bedroom_match = "maybe"

    if any(term.lower() in haystack for term in rules.utilities_included_positive):
        utilities_status = "included_yes"
    elif any(term.lower() in haystack for term in rules.utilities_included_partial):
        utilities_status = "partial"
    elif any(term.lower() in haystack for term in rules.utilities_separate_negative):
        utilities_status = "no"
    else:
        utilities_status = "unknown"

    location_match = not any(term.lower() in location_text for term in location_blacklist)

    evaluation = ListingEvaluation(
        listing_id=0,
        is_private=is_private,
        is_agency=is_agency,
        two_bedroom_match=bedroom_match,
        utilities_status=utilities_status,
        location_match=location_match,
    )
    evaluation.passes_realtime = is_private and bedroom_match == "yes" and location_match
    evaluation.passes_daily_digest = is_agency and bedroom_match == "yes" and location_match
    evaluation.reason_json = {
        "bedroom_match": bedroom_match,
        "utilities_status": utilities_status,
        "location_blacklist_applied": location_blacklist,
    }
    return evaluation
