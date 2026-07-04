from bs4 import BeautifulSoup


def _text_or_empty(node) -> str:
    return node.get_text(" ", strip=True) if node else ""


def parse_search_results(html: str) -> list[dict[str, object]]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, object]] = []
    for card in soup.select("[data-ad-id]"):
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



def parse_listing_detail(html: str, url: str) -> dict[str, object]:
    soup = BeautifulSoup(html, "html.parser")
    site_id = url.rstrip("/").split("-")[-1]
    contact_block = soup.select_one("#kontaktni-podatki") or soup.select_one(".contact-card")
    contact_text = _text_or_empty(contact_block)
    return {
        "site_id": site_id,
        "url": url,
        "title": _text_or_empty(soup.select_one("h1")),
        "description": _text_or_empty(soup.select_one(".description")),
        "price_text": _text_or_empty(soup.select_one(".price")),
        "area_text": _text_or_empty(soup.select_one(".area")),
        "location_text": _text_or_empty(soup.select_one(".location")),
        "contact_block": contact_text,
        "contact_type": "private" if "ZASEBNA PONUDBA" in contact_text else "agency",
    }
