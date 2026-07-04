from pathlib import Path

from nepremicnine_bot.parser import parse_listing_detail, parse_search_results


def test_parse_search_results_extracts_ids_and_urls():
    html = Path("tests/fixtures/search_results.html").read_text(encoding="utf-8")

    results = parse_search_results(html)

    assert results[0]["site_id"] == "1111111"
    assert results[0]["url"].startswith("https://www.nepremicnine.net/")


def test_parse_listing_detail_extracts_private_marker():
    html = Path("tests/fixtures/listing_private.html").read_text(encoding="utf-8")

    detail = parse_listing_detail(html, "https://www.nepremicnine.net/oglasi-oddaja/test-1111111/")

    assert detail["site_id"] == "1111111"
    assert detail["contact_type"] == "private"
    assert "ZASEBNA PONUDBA" in detail["contact_block"]
