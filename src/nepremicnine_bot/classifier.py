import re
import unicodedata

from nepremicnine_bot.models import ListingEvaluation, ListingFeatures, ListingSnapshot


WORD_NUMBERS = {
    'ena': 1,
    'eno': 1,
    'en': 1,
    'dve': 2,
    'dva': 2,
    'tri': 3,
    'stiri': 4,
    'four': 4,
    'three': 3,
    'two': 2,
    'one': 1,
}
FILLER = r'(?:\s+[a-z]+){0,3}'
BEDROOM_COUNT_PATTERNS = (
    re.compile(r'st\.?\s*spalnic\s*:\s*(\d+)'),
    re.compile(r'(\d+)\s*x\s*spalnic(?:a|e|i)?\b'),
    re.compile(r'(\d+)' + FILLER + r'\s+spalnic(?:a|e|i)?\b'),
    re.compile(r'\b(' + '|'.join(WORD_NUMBERS.keys()) + r')' + FILLER + r'\s+spalnic(?:a|e|i)?\b'),
)
ROOM_COUNT_PATTERN = re.compile(r'(\d+(?:[.,]\d+)?)\s*-?\s*sobno\b')
PLUS_UTILITIES_PATTERN = re.compile(r'\+\s*stroski\b')
UTILITIES_RANGE_PATTERN = re.compile(r'stroski\s+med\s+\d')
MONTHLY_UTILITIES_PATTERN = re.compile(r'mesecni\s+stroski\s*:')
NEGATIVE_UTILITIES_MARKERS = (
    'niso vkljuceni',
    'ni vkljuceno',
    'ne vkljucuje',
    'ne vkljucujejo',
    'placujejo posebej',
    'se placajo posebej',
    'obratovalni stroski niso',
)
POSITIVE_UTILITIES_MARKERS = (
    'stroski vkljuceni',
    'stroski so vkljuceni',
    'vkljuceni v ceno',
)
HEATING_RULES = (
    ('district', ('toplovod', 'daljinsko ogrevanje', 'daljinsko')),
    ('gas', ('ogrevanje na plin', 'plinsko ogrevanje')),
    ('electric', ('ogrevanje na elektriko', 'elektricno ogrevanje')),
    ('central', ('centralno ogrevanje',)),
)


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize('NFKD', value)
    ascii_only = ''.join(ch for ch in normalized if not unicodedata.combining(ch))
    return ' '.join(ascii_only.lower().split())



def _snapshot_sources(snapshot: ListingSnapshot) -> dict[str, str]:
    return {
        'search_title': snapshot.search_title,
        'search_location_text': snapshot.search_location_text,
        'detail_title': snapshot.detail_title,
        'detail_description': snapshot.detail_description,
        'detail_attributes_text': snapshot.detail_attributes_text,
        'detail_top_tab_text': snapshot.detail_top_tab_text,
        'detail_item_description': snapshot.detail_item_description,
        'detail_agency_text': snapshot.detail_agency_text,
        'contact_block': snapshot.contact_block,
    }



def _find_bedroom_counts(sources: dict[str, str]) -> tuple[dict[str, int], list[str], list[str]]:
    counts: dict[str, int] = {}
    positive_sources: list[str] = []
    negative_sources: list[str] = []
    for name, raw_value in sources.items():
        text = _normalize_text(raw_value)
        if not text:
            continue
        matched_count = None
        for pattern in BEDROOM_COUNT_PATTERNS:
            match = pattern.search(text)
            if not match:
                continue
            token = match.group(1)
            matched_count = int(token) if token.isdigit() else WORD_NUMBERS.get(token)
            if matched_count is not None:
                break
        if matched_count is not None:
            counts[name] = matched_count
            if matched_count == 2:
                positive_sources.append(name)
            else:
                negative_sources.append(name)
    return counts, positive_sources, negative_sources



def _find_room_count_hints(sources: dict[str, str]) -> tuple[dict[str, float], list[str], list[str]]:
    room_counts: dict[str, float] = {}
    strong_sources: list[str] = []
    weak_sources: list[str] = []
    for name, raw_value in sources.items():
        text = _normalize_text(raw_value)
        if not text:
            continue
        match = ROOM_COUNT_PATTERN.search(text)
        if not match:
            continue
        value = float(match.group(1).replace(',', '.'))
        room_counts[name] = value
        if value >= 2.5:
            strong_sources.append(name)
        elif value >= 2.0:
            weak_sources.append(name)
    return room_counts, strong_sources, weak_sources



def _find_term_sources(sources: dict[str, str], terms: list[str]) -> list[str]:
    normalized_terms = [_normalize_text(term) for term in terms]
    matched: list[str] = []
    for name, raw_value in sources.items():
        text = _normalize_text(raw_value)
        if text and any(term in text for term in normalized_terms):
            matched.append(name)
    return matched



def _resolve_heating(sources: dict[str, str]) -> tuple[str, str, list[str]]:
    for heating_type, markers in HEATING_RULES:
        matched_sources: list[str] = []
        for name, raw_value in sources.items():
            text = _normalize_text(raw_value)
            if text and any(marker in text for marker in markers):
                matched_sources.append(name)
        if matched_sources:
            return heating_type, ' '.join(sources[name] for name in matched_sources), matched_sources
    return 'unknown', '', []



def _is_negative_utilities_text(text: str) -> bool:
    if 'stros' not in text and 'najemnin' not in text and 'obratoval' not in text:
        return False
    if any(marker in text for marker in NEGATIVE_UTILITIES_MARKERS):
        return True
    return bool(
        PLUS_UTILITIES_PATTERN.search(text)
        or UTILITIES_RANGE_PATTERN.search(text)
        or MONTHLY_UTILITIES_PATTERN.search(text)
    )



def _is_positive_utilities_text(text: str) -> bool:
    if 'stros' not in text and 'cena' not in text:
        return False
    return any(marker in text for marker in POSITIVE_UTILITIES_MARKERS)



def _resolve_utilities(sources: dict[str, str], rules) -> tuple[str, str, list[str]]:
    negative_sources: list[str] = []
    for name, raw_value in sources.items():
        text = _normalize_text(raw_value)
        if _is_negative_utilities_text(text):
            negative_sources.append(name)
    if negative_sources:
        return 'no', ' '.join(sources[name] for name in negative_sources), negative_sources

    positive_sources: list[str] = []
    configured_positive = [_normalize_text(term) for term in rules.utilities_included_positive]
    configured_partial = [_normalize_text(term) for term in rules.utilities_included_partial]
    configured_negative = [_normalize_text(term) for term in rules.utilities_separate_negative]
    for name, raw_value in sources.items():
        text = _normalize_text(raw_value)
        if any(term in text for term in configured_negative):
            negative_sources.append(name)
        if _is_positive_utilities_text(text) or any(term in text for term in configured_positive):
            positive_sources.append(name)
    if negative_sources:
        return 'no', ' '.join(sources[name] for name in negative_sources), negative_sources
    if positive_sources:
        return 'included_yes', ' '.join(sources[name] for name in positive_sources), positive_sources

    partial_sources: list[str] = []
    for name, raw_value in sources.items():
        text = _normalize_text(raw_value)
        if any(term in text for term in configured_partial):
            partial_sources.append(name)
    if partial_sources:
        return 'partial', ' '.join(sources[name] for name in partial_sources), partial_sources
    return 'unknown', '', []



def extract_text_facts(snapshot: ListingSnapshot, rules, location_blacklist: list[str]) -> ListingFeatures:
    sources = _snapshot_sources(snapshot)
    counts, bedroom_positive_sources, bedroom_negative_sources = _find_bedroom_counts(sources)
    room_counts, strong_room_sources, weak_room_sources = _find_room_count_hints(sources)
    fallback_positive_sources = _find_term_sources(sources, rules.two_bedroom_positive)
    fallback_negative_sources = _find_term_sources(sources, rules.two_bedroom_negative)

    bedroom_sources = bedroom_positive_sources or fallback_positive_sources
    room_count_sources = strong_room_sources or weak_room_sources
    bedroom_conflict_sources: list[str] = []
    conflict_candidate_sources = [name for name in bedroom_negative_sources if counts.get(name) == 1]
    has_explicit_three_plus = any(counts.get(name, 0) > 2 for name in bedroom_negative_sources)
    if bedroom_sources:
        bedroom_count_guess = 2
        two_bedroom_match = 'yes'
    elif conflict_candidate_sources and strong_room_sources and not has_explicit_three_plus:
        bedroom_count_guess = 2
        two_bedroom_match = 'maybe'
        bedroom_conflict_sources = conflict_candidate_sources
    elif bedroom_negative_sources:
        first_negative = bedroom_negative_sources[0]
        bedroom_count_guess = counts[first_negative]
        two_bedroom_match = 'no'
    elif strong_room_sources:
        bedroom_count_guess = 2
        two_bedroom_match = 'yes'
    elif fallback_negative_sources:
        bedroom_count_guess = None
        two_bedroom_match = 'no'
    else:
        bedroom_count_guess = None
        two_bedroom_match = 'maybe'

    heating_type_norm, heating_text_raw, heating_sources = _resolve_heating(sources)
    utilities_status, utilities_text_raw, utilities_sources = _resolve_utilities(sources, rules)

    location_text = _normalize_text(snapshot.search_location_text)
    location_match = not any(_normalize_text(term) in location_text for term in location_blacklist)

    reason_json = {
        'bedroom_sources': bedroom_sources,
        'bedroom_conflict_sources': bedroom_conflict_sources,
        'room_count_sources': room_count_sources,
        'room_count_values': room_counts,
        'utilities_sources': utilities_sources,
        'heating_sources': heating_sources,
    }

    return ListingFeatures(
        listing_id=snapshot.listing_id,
        bedroom_count_guess=bedroom_count_guess,
        two_bedroom_match=two_bedroom_match,
        heating_text_raw=heating_text_raw,
        heating_type_norm=heating_type_norm,
        utilities_text_raw=utilities_text_raw,
        utilities_status=utilities_status,
        location_match=location_match,
        reason_json=reason_json,
    )



def _resolve_seller(snapshot: ListingSnapshot) -> tuple[bool, str]:
    agency_text = snapshot.detail_agency_text.strip()
    if agency_text:
        return 'ZASEBNA PONUDBA' in agency_text, 'detail_agency_text'
    contact_block = snapshot.contact_block.strip()
    return 'ZASEBNA PONUDBA' in contact_block, 'contact_block'



def evaluate_listing_facts(snapshot: ListingSnapshot, features: ListingFeatures, rules) -> ListingEvaluation:
    is_private, seller_source = _resolve_seller(snapshot)
    evaluation = ListingEvaluation(
        listing_id=snapshot.listing_id,
        is_private=is_private,
        is_agency=not is_private,
        two_bedroom_match=features.two_bedroom_match,
        utilities_status=features.utilities_status,
        location_match=features.location_match,
    )
    evaluation.feature_flags = dict(features.feature_flags)
    evaluation.passes_realtime = is_private and features.two_bedroom_match == 'yes' and features.location_match
    evaluation.passes_daily_digest = (not is_private) and features.two_bedroom_match == 'yes' and features.location_match
    evaluation.reason_json = {
        'bedroom_match': features.two_bedroom_match,
        'bedroom_sources': features.reason_json.get('bedroom_sources', []),
        'bedroom_conflict_sources': features.reason_json.get('bedroom_conflict_sources', []),
        'room_count_sources': features.reason_json.get('room_count_sources', []),
        'room_count_values': features.reason_json.get('room_count_values', {}),
        'utilities_status': features.utilities_status,
        'utilities_sources': features.reason_json.get('utilities_sources', []),
        'heating_type_norm': features.heating_type_norm,
        'heating_sources': features.reason_json.get('heating_sources', []),
        'location_match': features.location_match,
        'seller_source': seller_source,
    }
    return evaluation



def classify_listing(detail: dict[str, object], rules, location_blacklist: list[str]) -> ListingEvaluation:
    snapshot = ListingSnapshot(
        listing_id=0,
        source_url=str(detail.get('url', '')),
        search_title=str(detail.get('title', '')),
        search_price_text=str(detail.get('price_text', '')),
        search_area_text=str(detail.get('area_text', '')),
        search_location_text=str(detail.get('location_text', '')),
        detail_title=str(detail.get('title', '')),
        detail_description=str(detail.get('description', '')),
        contact_block=str(detail.get('contact_block', '')),
        published_at_text=str(detail.get('published_at_text', '')),
        content_hash=str(detail.get('content_hash', '')),
        detail_attributes_text=str(detail.get('attributes_text', '')),
        detail_top_tab_text=str(detail.get('top_tab_text', '')),
        detail_item_description=str(detail.get('item_description_text', '')),
        detail_agency_text=str(detail.get('agency_text', '')),
    )
    features = extract_text_facts(snapshot, rules, location_blacklist)
    return evaluate_listing_facts(snapshot, features, rules)
