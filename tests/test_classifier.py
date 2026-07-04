from nepremicnine_bot.classifier import classify_listing
from nepremicnine_bot.config import RuleSet



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
