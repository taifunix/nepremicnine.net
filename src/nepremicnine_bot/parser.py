import re
from hashlib import sha1
from urllib.parse import urljoin, urlsplit

from bs4 import BeautifulSoup

from nepremicnine_bot.models import ListingSnapshot


SITE_ID_PATTERN = re.compile(r'_(\d+)/?$')
AREA_PATTERN = re.compile(r'\d+(?:[.,]\d+)?\s*m\s*2')
ROOM_COUNT_TEXT_PATTERN = re.compile(r'\b\d+(?:[.,]\d+)?-sobno\b', re.IGNORECASE)
REGION_PATTERN = re.compile(r'Regija:\s*([^|\n<]+)', re.IGNORECASE)
ISO_DATE_PATTERN = re.compile(r'(\d{4}-\d{2}-\d{2})')
PAGE_NUMBER_PATTERN = re.compile(r'(?:[?&](?:stran|page)=|/stran-)(\d+)', re.IGNORECASE)


def _text_or_empty(node) -> str:
    return node.get_text(" ", strip=True) if node else ""



def _normalize_snapshot_text(value: str) -> str:
    return " ".join(value.split())



def _site_id_from_url(url: str) -> str:
    match = SITE_ID_PATTERN.search(url.strip())
    return match.group(1) if match else ""



def _first_non_empty(*values: str) -> str:
    for value in values:
        if value and value.strip():
            return value.strip()
    return ""



def _extract_area_text(title: str, summary: str) -> str:
    for source in (summary, title):
        match = AREA_PATTERN.search(source)
        if match:
            return match.group(0)
    return ""



def _extract_location_text(title: str) -> str:
    if not title:
        return ""
    area_match = AREA_PATTERN.search(title)
    if area_match:
        return title[: area_match.start()].rstrip(" ,")
    return title.split(" - ", 1)[0].strip()



def _extract_contact_block(soup: BeautifulSoup) -> str:
    contact_block = soup.select_one("#kontaktni-podatki") or soup.select_one(".contact-card")
    if contact_block:
        return _text_or_empty(contact_block)

    agency = _extract_agency_text(soup)
    if agency:
        return agency

    header = soup.find(["h4", "h5"], string=lambda value: isinstance(value, str) and "Kontaktni podatki" in value)
    return _text_or_empty(header)



def _extract_agency_text(soup: BeautifulSoup) -> str:
    agency_nodes = soup.select("#agency")
    for node in agency_nodes:
        text = _text_or_empty(node)
        lowered = text.lower()
        if "kontaktni podatki" in lowered or "zasebna ponudba" in lowered:
            return text
    return _text_or_empty(agency_nodes[0]) if agency_nodes else ""



def _extract_item_description_text(soup: BeautifulSoup) -> str:
    values = []
    for node in soup.select('[itemprop="description"]'):
        text = _text_or_empty(node)
        if text and text not in values:
            values.append(text)
    return " ".join(values)



def _extract_room_count_text(title: str, item_description_text: str, attributes_text: str, top_tab_text: str) -> str:
    for source in (title, item_description_text, attributes_text, top_tab_text):
        match = ROOM_COUNT_TEXT_PATTERN.search(source)
        if match:
            return match.group(0)
    return ""



def _extract_region_text(soup: BeautifulSoup, top_tab_text: str) -> str:
    for source in (top_tab_text, _text_or_empty(soup.select_one('#top-tabContent'))):
        match = REGION_PATTERN.search(source)
        if match:
            return match.group(1).strip()
    return ""



def _extract_display_date_text(published_at_text: str) -> str:
    match = ISO_DATE_PATTERN.search(published_at_text)
    return match.group(1) if match else published_at_text.strip()



def _extract_page_number(url: str) -> int | None:
    match = PAGE_NUMBER_PATTERN.search(url)
    if not match:
        return None
    return int(match.group(1))



def parse_search_results(html: str) -> list[dict[str, object]]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, object]] = []

    legacy_cards = soup.select("[data-ad-id]")
    if legacy_cards:
        for card in legacy_cards:
            site_id = card.get("data-ad-id", "").strip()
            link = card.select_one("a")
            if not site_id or not link or not link.get("href"):
                continue
            results.append(
                {
                    "site_id": site_id,
                    "url": link["href"],
                    "title": _text_or_empty(card.select_one(".title")),
                    "price_text": _text_or_empty(card.select_one(".price")),
                    "area_text": _text_or_empty(card.select_one(".area")),
                    "location_text": _text_or_empty(card.select_one(".location")),
                }
            )
        return results

    for card in soup.select(".property-box"):
        details = card.select_one(".property-details")
        url = ""
        if details and details.get("data-href"):
            url = str(details.get("data-href", "")).strip()
        if not url:
            meta = card.select_one('meta[itemprop="mainEntityOfPage"]')
            url = str(meta.get("content", "")).strip() if meta else ""
        if not url:
            link = card.select_one('a[href*="/oglasi-oddaja/"]')
            url = str(link.get("href", "")).strip() if link else ""
        site_id = _site_id_from_url(url)
        if not site_id or not url:
            continue

        title_node = card.select_one(".url-title-d h2") or card.select_one(".url-title-m h2") or card.select_one("h2")
        price_node = card.select_one("h6")
        area_node = card.select_one('ul[itemprop="disambiguatingDescription"] li')
        location_node = card.select_one(".url-title-d") or card.select_one(".url-title-m")

        results.append(
            {
                "site_id": site_id,
                "url": url,
                "title": _text_or_empty(title_node),
                "price_text": _text_or_empty(price_node),
                "area_text": _text_or_empty(area_node),
                "location_text": _text_or_empty(location_node),
            }
        )
    return results



def parse_search_total_items(html: str) -> int | None:
    soup = BeautifulSoup(html, "html.parser")
    meta = soup.select_one('meta[itemprop="numberOfItems"]')
    if not meta:
        return None
    content = str(meta.get("content", "")).strip()
    digits = re.findall(r"\d+", content)
    if not digits:
        return None
    return int("".join(digits))



def parse_search_pagination_links(html: str, current_url: str) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    current_page_number = _extract_page_number(current_url) or 1
    normalized_current = urlsplit(current_url).geturl()
    candidates: list[tuple[int, str]] = []
    seen_urls: set[str] = set()

    selectors = (
        "#pagination a[href]",
        ".pagination a[href]",
        'a[rel="next"][href]',
        'a[href*="stran="]',
        'a[href*="page="]',
        'a[href*="/stran-"]',
    )
    for selector in selectors:
        for node in soup.select(selector):
            href = str(node.get("href", "")).strip()
            if not href:
                continue
            absolute_url = urljoin(current_url, href)
            normalized = urlsplit(absolute_url).geturl()
            if normalized == normalized_current or normalized in seen_urls:
                continue
            page_number = _extract_page_number(normalized)
            if page_number is not None and page_number <= current_page_number:
                continue
            seen_urls.add(normalized)
            candidates.append((page_number or 10**9, normalized))

    candidates.sort(key=lambda item: (item[0], item[1]))
    return [url for _, url in candidates]



def parse_listing_detail(html: str, url: str) -> dict[str, object]:
    soup = BeautifulSoup(html, "html.parser")
    site_id = _site_id_from_url(url) or url.rstrip("/").split("-")[-1]
    title = _text_or_empty(soup.select_one("h1"))
    item_description_text = _extract_item_description_text(soup)
    attributes_text = _text_or_empty(soup.select_one("#atributi"))
    top_tab_text = _text_or_empty(soup.select_one("#top-tabContent"))
    agency_text = _extract_agency_text(soup)
    room_count_text = _extract_room_count_text(title, item_description_text, attributes_text, top_tab_text)
    region_text = _extract_region_text(soup, top_tab_text)
    published_at_text = _text_or_empty(soup.select_one(".published-at"))
    display_date_text = _extract_display_date_text(published_at_text)
    summary = _first_non_empty(
        _text_or_empty(soup.select_one(".description")),
        _text_or_empty(soup.select_one('.detail_main_desc strong.fs-15')),
        _text_or_empty(soup.find("strong", class_="fs-15", string=lambda value: isinstance(value, str) and "Cena:" in value)),
        item_description_text,
        str((soup.select_one('meta[name="Description"]') or {}).get("content", "")),
        str((soup.select_one('meta[property="og:description"]') or {}).get("content", "")),
    )
    price_text = _first_non_empty(_text_or_empty(soup.select_one(".price")), _text_or_empty(soup.select_one(".cena")))
    area_text = _first_non_empty(_text_or_empty(soup.select_one(".area")), _extract_area_text(title, summary))
    location_text = _first_non_empty(_text_or_empty(soup.select_one(".location")), _extract_location_text(title))
    contact_text = _extract_contact_block(soup)
    return {
        "site_id": site_id,
        "url": url,
        "title": title,
        "description": summary,
        "price_text": price_text,
        "area_text": area_text,
        "location_text": location_text,
        "published_at_text": published_at_text,
        "display_date_text": display_date_text,
        "room_count_text": room_count_text,
        "region_text": region_text,
        "contact_block": contact_text,
        "contact_type": "private" if "ZASEBNA PONUDBA" in contact_text else "agency",
        "attributes_text": attributes_text,
        "top_tab_text": top_tab_text,
        "item_description_text": item_description_text,
        "agency_text": agency_text,
    }



def build_listing_snapshot(listing_id: int, search_result: dict[str, object], detail: dict[str, object]) -> ListingSnapshot:
    search_title = _normalize_snapshot_text(str(search_result.get("title", "")))
    search_price_text = _normalize_snapshot_text(str(search_result.get("price_text", "")))
    search_area_text = _normalize_snapshot_text(str(search_result.get("area_text", "")))
    search_location_text = _normalize_snapshot_text(str(search_result.get("location_text", "")))
    detail_title = _normalize_snapshot_text(str(detail.get("title", "")))
    detail_description = _normalize_snapshot_text(str(detail.get("description", "")))
    contact_block = _normalize_snapshot_text(str(detail.get("contact_block", "")))
    published_at_text = _normalize_snapshot_text(str(detail.get("published_at_text", "")))
    detail_attributes_text = _normalize_snapshot_text(str(detail.get("attributes_text", "")))
    detail_top_tab_text = _normalize_snapshot_text(str(detail.get("top_tab_text", "")))
    detail_item_description = _normalize_snapshot_text(str(detail.get("item_description_text", "")))
    detail_agency_text = _normalize_snapshot_text(str(detail.get("agency_text", "")))
    room_count_text = _normalize_snapshot_text(str(detail.get("room_count_text", "")))
    region_text = _normalize_snapshot_text(str(detail.get("region_text", "")))
    display_date_text = _normalize_snapshot_text(str(detail.get("display_date_text", "")))
    hash_payload = "|".join(
        [
            search_title,
            search_price_text,
            search_area_text,
            search_location_text,
            detail_title,
            detail_description,
            contact_block,
            published_at_text,
            detail_attributes_text,
            detail_top_tab_text,
            detail_item_description,
            detail_agency_text,
            room_count_text,
            region_text,
            display_date_text,
        ]
    )
    return ListingSnapshot(
        listing_id=listing_id,
        source_url=str(detail.get("url", "")),
        search_title=search_title,
        search_price_text=search_price_text,
        search_area_text=search_area_text,
        search_location_text=search_location_text,
        detail_title=detail_title,
        detail_description=detail_description,
        contact_block=contact_block,
        published_at_text=published_at_text,
        content_hash=sha1(hash_payload.encode("utf-8")).hexdigest(),
        detail_attributes_text=detail_attributes_text,
        detail_top_tab_text=detail_top_tab_text,
        detail_item_description=detail_item_description,
        detail_agency_text=detail_agency_text,
        room_count_text=room_count_text,
        region_text=region_text,
        display_date_text=display_date_text,
    )
