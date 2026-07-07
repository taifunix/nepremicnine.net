from nepremicnine_bot.classifier import classify_listing, evaluate_listing_facts, extract_text_facts
from nepremicnine_bot.config import RuleSet
from nepremicnine_bot.models import ListingSnapshot


def test_classify_private_two_bedroom_listing():
    rules = RuleSet()
    detail = {
        "title": "Stanovanje, 2 spalnici, oddaja",
        "description": "V ceno so stroski vkljuceni. ZASEBNA PONUDBA.",
        "location_text": "Ljubljana Center",
        "contact_block": "Kontaktni podatki ZASEBNA PONUDBA",
    }

    evaluation = classify_listing(detail, rules, ["siska"])

    assert evaluation.is_private is True
    assert evaluation.two_bedroom_match == "yes"
    assert evaluation.utilities_status == "included_yes"
    assert evaluation.location_match is True


def test_classify_blacklisted_location_and_agency():
    rules = RuleSet()
    detail = {
        "title": "Oddaja trisobno stanovanje",
        "description": "Stroski niso vkljuceni.",
        "location_text": "Ljubljana Siska",
        "contact_block": "Kontaktni podatki Agencija X",
    }

    evaluation = classify_listing(detail, rules, ["siska"])

    assert evaluation.is_agency is True
    assert evaluation.location_match is False


def test_extract_text_facts_detects_bedrooms_utilities_and_heating():
    snapshot = ListingSnapshot(
        listing_id=1,
        source_url="https://example.com/1",
        search_title="Stanovanje 2 spalnici",
        search_price_text="1.200 EUR/mesec",
        search_area_text="60 m2",
        search_location_text="Ljubljana Center",
        detail_title="Stanovanje 2 spalnici",
        detail_description="Centralno ogrevanje. Stroški vključeni.",
        contact_block="Kontaktni podatki ZASEBNA PONUDBA",
        published_at_text="danes",
        content_hash="hash-1",
    )

    features = extract_text_facts(snapshot, RuleSet(), ["siska"])

    assert features.bedroom_count_guess == 2
    assert features.two_bedroom_match == "yes"
    assert features.heating_type_norm == "central"
    assert features.utilities_status == "included_yes"
    assert features.location_match is True


def test_extract_text_facts_uses_spalnic_not_sobno_and_tracks_sources():
    snapshot = ListingSnapshot(
        listing_id=1,
        source_url="https://example.com/1",
        search_title="Stanovanje 2-sobno",
        search_price_text="950 EUR/mesec",
        search_area_text="63 m2",
        search_location_text="Ljubljana Center",
        detail_title="BEŽIGRAJSKI DVOR, SAVSKI KAMEN, 63 m 2 - oddaja, stanovanje, 2-sobno",
        detail_description="63 m2, 2-sobno, zgrajeno l. 2010, 1/4 nad., oddamo.",
        contact_block="Kontaktni podatki ZASEBNA PONUDBA 041 217 765",
        published_at_text="danes",
        content_hash="hash-1",
        detail_attributes_text="Velikost: 63,00 m 2 Št. spalnic: 2 Stroški: vključeni v ceno Ogrevanje z radiatorji",
        detail_top_tab_text="Dodaten opis nepremičnine Stanovanje ima dve spalnici in stroški so vključeni.",
        detail_item_description="63 m2, 2-sobno, zgrajeno l. 2010, 1/4 nad., oddamo. Cena: cca 1.000,00 EUR/mes",
        detail_agency_text="Kontaktni podatki ZASEBNA PONUDBA 041 217 765",
    )

    features = extract_text_facts(snapshot, RuleSet(), ["siska"])
    evaluation = evaluate_listing_facts(snapshot, features, RuleSet())

    assert features.bedroom_count_guess == 2
    assert features.two_bedroom_match == "yes"
    assert features.utilities_status == "included_yes"
    assert features.reason_json["bedroom_sources"] == ["detail_attributes_text", "detail_top_tab_text"]
    assert features.reason_json["utilities_sources"] == ["detail_attributes_text", "detail_top_tab_text"]
    assert evaluation.is_private is True


def test_extract_text_facts_uses_room_count_for_two_point_five_and_up():
    snapshot = ListingSnapshot(
        listing_id=4,
        source_url="https://example.com/4",
        search_title="Stanovanje 2,5-sobno",
        search_price_text="980 EUR/mesec",
        search_area_text="70 m2",
        search_location_text="Ljubljana Center",
        detail_title="Center, 70 m 2 - oddaja, stanovanje, 2,5-sobno",
        detail_description="Lepo stanovanje z ločeno kuhinjo.",
        contact_block="Kontaktni podatki ZASEBNA PONUDBA",
        published_at_text="danes",
        content_hash="hash-4",
        detail_top_tab_text="Razporeditev prostorov: kuhinja z dnevnim prostorom in spalnica.",
        detail_item_description="70 m2, 2,5-sobno, oddamo.",
        detail_agency_text="Kontaktni podatki ZASEBNA PONUDBA",
    )

    features = extract_text_facts(snapshot, RuleSet(), ["siska"])

    assert features.bedroom_count_guess == 2
    assert features.two_bedroom_match == "yes"
    assert features.reason_json["room_count_sources"] == ["search_title", "detail_title", "detail_item_description"]


def test_extract_text_facts_detects_bedrooms_from_free_text_and_negative_utilities():
    snapshot = ListingSnapshot(
        listing_id=3,
        source_url="https://example.com/3",
        search_title="Stanovanje 2,5-sobno",
        search_price_text="950 EUR/mesec",
        search_area_text="69 m2",
        search_location_text="Ljubljana Center",
        detail_title="BS 3, VOJKOVA, 69,5 m 2 - oddaja, stanovanje, 2,5-sobno",
        detail_description="Lepo stanovanje, prenovljeno in opremljeno.",
        contact_block="Kontaktni podatki ABC nepremičnine d.o.o.",
        published_at_text="danes",
        content_hash="hash-3",
        detail_attributes_text="Velikost: 69,50 m 2 Št. spalnic: 2 Ogrevanje z radiatorji",
        detail_top_tab_text="Razporeditev prostorov: kuhinja z dnevnim prostorom, 2 ločeni spalnici. V najemnino niso vključeni mesečni stroški.",
        detail_item_description="69,5 m2, 2,5-sobno, adaptirano l. 2026.",
        detail_agency_text="Kontaktni podatki ABC nepremičnine d.o.o.",
    )

    features = extract_text_facts(snapshot, RuleSet(), ["siska"])

    assert features.bedroom_count_guess == 2
    assert features.two_bedroom_match == "yes"
    assert features.utilities_status == "no"
    assert features.reason_json["bedroom_sources"] == ["detail_attributes_text", "detail_top_tab_text"]
    assert features.reason_json["utilities_sources"] == ["detail_top_tab_text"]


def test_extract_text_facts_marks_room_conflict_as_maybe_and_plus_stroski_as_separate():
    snapshot = ListingSnapshot(
        listing_id=5,
        source_url="https://example.com/5",
        search_title="Stanovanje 2,5-sobno",
        search_price_text="800 EUR/mesec",
        search_area_text="60 m2",
        search_location_text="Ljubljana Siska",
        detail_title="LJUBLJANA ŠIŠKA, 60 m 2 - oddaja, stanovanje, 2,5-sobno",
        detail_description="Svetlo stanovanje.",
        contact_block="Kontaktni podatki ZASEBNA PONUDBA",
        published_at_text="danes",
        content_hash="hash-5",
        detail_attributes_text="Velikost: 60,00 m 2 Št. spalnic: 1 Ogrevanje z radiatorji",
        detail_top_tab_text="Oddaja se 2-sobno stanovanje. Prostori: dnevna soba, ločena spalnica, kuhinja z jedilnico. Mesečna najemnina: 800 EUR + stroški.",
        detail_item_description="LJ. ŠIŠKA, 60 m2, 2,5-sobno, oddamo. Cena: 800,00 EUR/mes",
        detail_agency_text="Kontaktni podatki ZASEBNA PONUDBA",
    )

    features = extract_text_facts(snapshot, RuleSet(), [])

    assert features.bedroom_count_guess == 2
    assert features.two_bedroom_match == "maybe"
    assert features.utilities_status == "no"
    assert features.reason_json["room_count_sources"] == ["search_title", "detail_title", "detail_item_description"]
    assert features.reason_json["utilities_sources"] == ["detail_top_tab_text"]


def test_extract_text_facts_detects_2x_spalnica_and_common_heating_markers():
    snapshot = ListingSnapshot(
        listing_id=6,
        source_url="https://example.com/6",
        search_title="Stanovanje 3-sobno",
        search_price_text="850 EUR/mesec",
        search_area_text="72 m2",
        search_location_text="Ljubljana Siska",
        detail_title="ZG. ŠIŠKA, 72,4 m 2 - oddaja, stanovanje, 3-sobno",
        detail_description="Lepo stanovanje.",
        contact_block="Kontaktni podatki Agencija X",
        published_at_text="danes",
        content_hash="hash-6",
        detail_attributes_text="Velikost: 72,40 m 2 Ogrevanje na plin",
        detail_top_tab_text="Oddamo 3-sobno stanovanje. 2x spalnica, velik dnevno-bivalen prostor. mesečni stroški: upravnik 130 EUR, elektrika 30 EUR, ogrevanje 120-260 EUR.",
        detail_item_description="72,4 m2, 3-sobno, oddamo.",
        detail_agency_text="Kontaktni podatki Agencija X",
    )

    features = extract_text_facts(snapshot, RuleSet(), [])

    assert features.bedroom_count_guess == 2
    assert features.two_bedroom_match == "yes"
    assert features.heating_type_norm == "gas"
    assert features.utilities_status == "no"
    assert features.reason_json["bedroom_sources"] == ["detail_top_tab_text"]
    assert features.reason_json["utilities_sources"] == ["detail_top_tab_text"]


def test_extract_text_facts_keeps_three_bedroom_listing_out_even_with_strong_room_count():
    snapshot = ListingSnapshot(
        listing_id=7,
        source_url="https://example.com/7",
        search_title="Stanovanje 4-sobno",
        search_price_text="1200 EUR/mesec",
        search_area_text="104 m2",
        search_location_text="Ljubljana Vic",
        detail_title="LJUBLJANA VIC, 104.5 m 2 - oddaja, stanovanje, 4-sobno",
        detail_description="Prostorno stanovanje.",
        contact_block="Kontaktni podatki Agencija X",
        published_at_text="danes",
        content_hash="hash-7",
        detail_attributes_text="Velikost: 104,50 m 2 St. spalnic: 3 St. kopalnic: 1",
        detail_top_tab_text="Oddamo prostorno 4-sobno stanovanje.",
        detail_item_description="104,5 m2, 4-sobno, oddamo.",
        detail_agency_text="Kontaktni podatki Agencija X",
    )

    features = extract_text_facts(snapshot, RuleSet(), [])

    assert features.bedroom_count_guess == 3
    assert features.two_bedroom_match == "no"
    assert features.reason_json["bedroom_conflict_sources"] == []


def test_extract_text_facts_detects_agency_from_agency_block():
    snapshot = ListingSnapshot(
        listing_id=2,
        source_url="https://example.com/2",
        search_title="Stanovanje 2-sobno",
        search_price_text="950 EUR/mesec",
        search_area_text="69 m2",
        search_location_text="Ljubljana Center",
        detail_title="BS 3, VOJKOVA, 69,5 m 2 - oddaja, stanovanje, 2,5-sobno",
        detail_description="Lepo stanovanje. Stroški niso vključeni.",
        contact_block="Kontaktni podatki ABC nepremičnine d.o.o.",
        published_at_text="danes",
        content_hash="hash-2",
        detail_attributes_text="Velikost: 69,50 m 2 Št. spalnic: 1",
        detail_top_tab_text="Dodaten opis nepremičnine kuhinja z dnevnim prostorom in ena spalnica.",
        detail_item_description="69,5 m2, 2,5-sobno, adaptirano l. 2026.",
        detail_agency_text="Kontaktni podatki ABC nepremičnine d.o.o.",
    )

    features = extract_text_facts(snapshot, RuleSet(), ["siska"])
    evaluation = evaluate_listing_facts(snapshot, features, RuleSet())

    assert features.two_bedroom_match == "maybe"
    assert evaluation.is_agency is True
    assert evaluation.is_private is False
    assert evaluation.reason_json["seller_source"] == "detail_agency_text"


def test_evaluate_listing_facts_marks_filtered_listing_without_notification():
    snapshot = ListingSnapshot(
        listing_id=1,
        source_url="https://example.com/1",
        search_title="Garsonjera",
        search_price_text="900 EUR/mesec",
        search_area_text="30 m2",
        search_location_text="Ljubljana Siska",
        detail_title="Garsonjera",
        detail_description="Električno ogrevanje. Stroški niso vključeni.",
        contact_block="Kontaktni podatki ZASEBNA PONUDBA",
        published_at_text="danes",
        content_hash="hash-2",
    )
    features = extract_text_facts(snapshot, RuleSet(), ["siska"])

    evaluation = evaluate_listing_facts(snapshot, features, RuleSet())

    assert evaluation.passes_realtime is False
    assert evaluation.reason_json["bedroom_match"] == "no"


