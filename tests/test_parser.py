from pathlib import Path

from nepremicnine_bot.parser import (
    build_listing_snapshot,
    parse_listing_detail,
    parse_search_pagination_links,
    parse_search_results,
    parse_search_total_items,
)


def test_parse_search_results_extracts_ids_and_urls():
    html = Path("tests/fixtures/search_results.html").read_text(encoding="utf-8")

    results = parse_search_results(html)

    assert results[0]["site_id"] == "1111111"
    assert results[0]["url"].startswith("https://www.nepremicnine.net/")


def test_parse_search_results_extracts_live_property_boxes():
    html = """
    <html><body>
      <div class="property-box property-normal mt-4 mt-md-0" itemprop="item" itemscope="" itemtype="http://schema.org/Offer">
        <meta itemprop="mainEntityOfPage" content="https://www.nepremicnine.net/oglasi-oddaja/bezigrajski-dvor-savski-kamen-stanovanje_7378193/">
        <div class="property-details" data-href="https://www.nepremicnine.net/oglasi-oddaja/bezigrajski-dvor-savski-kamen-stanovanje_7378193/">
          <span class="font-roboto">
            Oddaja: Stanovanje,
            <span class="tipi">2-sobno</span>
          </span>
          <a href="https://www.nepremicnine.net/oglasi-oddaja/bezigrajski-dvor-savski-kamen-stanovanje_7378193/" itemprop="name" title="BEŽIGRAJSKI DVOR, SAVSKI KAMEN" class="url-title-d">
            <h2>BEŽIGRAJSKI DVOR, SAVSKI KAMEN</h2>
          </a>
          <p class="font-roboto hidden-m" itemprop="description">
            63 m2, 2-sobno, zgrajeno l. 2010, 1/4 nad., oddamo. Cena: cca 1.000,00 EUR/mes
          </p>
          <ul itemprop="disambiguatingDescription">
            <li>63,00 m<sup>2</sup></li>
            <li>2010</li>
            <li>1/4</li>
          </ul>
          <h6>1.000,00 EUR/mesec</h6>
          <div class="property-btn d-flex" itemprop="seller" itemscope="" itemtype="http://schema.org/Person">
            <span class="me-2">Zasebna ponudba</span>
          </div>
        </div>
      </div>
    </body></html>
    """

    results = parse_search_results(html)

    assert len(results) == 1
    assert results[0]["site_id"] == "7378193"
    assert results[0]["url"] == "https://www.nepremicnine.net/oglasi-oddaja/bezigrajski-dvor-savski-kamen-stanovanje_7378193/"
    assert results[0]["title"] == "BEŽIGRAJSKI DVOR, SAVSKI KAMEN"
    assert results[0]["price_text"] == "1.000,00 EUR/mesec"
    assert results[0]["area_text"] == "63,00 m 2"
    assert results[0]["location_text"] == "BEŽIGRAJSKI DVOR, SAVSKI KAMEN"


def test_parse_search_pagination_links_and_total_items():
    html = """
    <html><body>
      <meta itemprop="numberOfItems" content="45">
      <div id="pagination">
        <a href="/oglasi-oddaja/ljubljana-mesto/stanovanje/?last=7&amp;stran=2">2</a>
        <a href="https://www.nepremicnine.net/oglasi-oddaja/ljubljana-mesto/stanovanje/?last=7&amp;stran=3">3</a>
        <a href="/oglasi-oddaja/ljubljana-mesto/stanovanje/?last=7">1</a>
      </div>
    </body></html>
    """

    links = parse_search_pagination_links(
        html,
        "https://www.nepremicnine.net/oglasi-oddaja/ljubljana-mesto/stanovanje/?last=7",
    )

    assert links == [
        "https://www.nepremicnine.net/oglasi-oddaja/ljubljana-mesto/stanovanje/?last=7&stran=2",
        "https://www.nepremicnine.net/oglasi-oddaja/ljubljana-mesto/stanovanje/?last=7&stran=3",
    ]
    assert parse_search_total_items(html) == 45


def test_parse_listing_detail_extracts_private_marker():
    html = Path("tests/fixtures/listing_private.html").read_text(encoding="utf-8")

    detail = parse_listing_detail(html, "https://www.nepremicnine.net/oglasi-oddaja/test-1111111/")

    assert detail["site_id"] == "1111111"
    assert detail["contact_type"] == "private"
    assert "ZASEBNA PONUDBA" in detail["contact_block"]


def test_parse_listing_detail_extracts_live_page_fields():
    html = """
    <html><body>
      <div id="agency">
        <h4 class="content-title">Kontaktni podatki</h4>
        <h5 class="mt-3 roboto">ZASEBNA PONUDBA</h5>
        <div class="kontakt_info">041 217 765</div>
      </div>
      <h1 class="mb-0" itemprop="name">BEŽIGRAJSKI DVOR, SAVSKI KAMEN, 63 m<sup>2</sup> <span class="fw-300"> - oddaja, stanovanje, 2-sobno</span></h1>
      <div class="cena"><span class="me-4"> cca 1.000,00 EUR/mesec</span></div>
      <strong class="fs-15">BEŽIGRAJSKI DVOR, SAVSKI KAMEN, 63 m2, 2-sobno, zgrajeno l. 2010, 1/4 nad., oddamo. Cena: cca 1.000,00 EUR/mes</strong>
      <ul id="atributi">
        <li>Velikost: 63,00 m<sup>2</sup></li>
        <li>Št. spalnic: 2</li>
        <li>Stroški: vključeni v ceno</li>
      </ul>
      <div class="tab-content" id="top-tabContent">
        <h4>Dodaten opis nepremičnine</h4>
        <p>Stanovanje ima dve spalnici in stroški so vključeni.</p>
      </div>
      <div>Referenčna št.: <strong class="fs-15">7378193</strong></div>
    </body></html>
    """

    detail = parse_listing_detail(html, "https://www.nepremicnine.net/oglasi-oddaja/bezigrajski-dvor-savski-kamen-stanovanje_7378193/")

    assert detail["site_id"] == "7378193"
    assert detail["title"] == "BEŽIGRAJSKI DVOR, SAVSKI KAMEN, 63 m 2 - oddaja, stanovanje, 2-sobno"
    assert detail["description"] == "BEŽIGRAJSKI DVOR, SAVSKI KAMEN, 63 m2, 2-sobno, zgrajeno l. 2010, 1/4 nad., oddamo. Cena: cca 1.000,00 EUR/mes"
    assert detail["price_text"] == "cca 1.000,00 EUR/mesec"
    assert detail["attributes_text"] == "Velikost: 63,00 m 2 Št. spalnic: 2 Stroški: vključeni v ceno"
    assert detail["top_tab_text"] == "Dodaten opis nepremičnine Stanovanje ima dve spalnici in stroški so vključeni."
    assert detail["agency_text"] == "Kontaktni podatki ZASEBNA PONUDBA 041 217 765"
    assert detail["contact_type"] == "private"


def test_parse_listing_detail_extracts_region_room_count_and_date_fields():
    html = """
    <html><body>
      <h1>DOMŽALE, 60 m 2 - oddaja, stanovanje, 2,5-sobno</h1>
      <div id="top-tabContent">
        <div>Regija: Osrednjeslovenska</div>
      </div>
      <div class="published-at">Objavljeno: 2026-07-06</div>
    </body></html>
    """

    detail = parse_listing_detail(html, "https://www.nepremicnine.net/oglasi-oddaja/domzale-stanovanje_123/")

    assert detail["region_text"] == "Osrednjeslovenska"
    assert detail["room_count_text"] == "2,5-sobno"
    assert detail["published_at_text"] == "Objavljeno: 2026-07-06"
    assert detail["display_date_text"] == "2026-07-06"


def test_build_listing_snapshot_combines_search_and_detail_fields():
    search_html = Path("tests/fixtures/search_results.html").read_text(encoding="utf-8")
    detail_html = Path("tests/fixtures/listing_private.html").read_text(encoding="utf-8")

    search_result = parse_search_results(search_html)[0]
    detail = parse_listing_detail(detail_html, "https://www.nepremicnine.net/oglasi-oddaja/test-1111111/")

    snapshot = build_listing_snapshot(listing_id=1, search_result=search_result, detail=detail)

    assert snapshot.listing_id == 1
    assert snapshot.search_title == "Stanovanje 2 spalnici"
    assert "Stroški vključeni" in snapshot.detail_description
    assert snapshot.contact_block.startswith("Kontaktni podatki")
    assert snapshot.content_hash
