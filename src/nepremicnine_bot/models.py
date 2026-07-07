from dataclasses import dataclass, field
from datetime import datetime


@dataclass(slots=True)
class Listing:
    site_id: str
    url: str
    title: str
    price_current: int
    area: float
    location_text: str
    id: int | None = None
    published_at_text: str | None = None
    content_hash: str | None = None
    first_seen_at: datetime | None = None
    last_seen_at: datetime | None = None
    is_active: bool = True


@dataclass(slots=True)
class ListingEvaluation:
    listing_id: int
    is_private: bool
    is_agency: bool
    two_bedroom_match: str
    utilities_status: str
    location_match: bool
    feature_flags: dict[str, str] = field(default_factory=dict)
    passes_realtime: bool = False
    passes_daily_digest: bool = False
    reason_json: dict[str, object] = field(default_factory=dict)
    evaluated_at: datetime | None = None


@dataclass(slots=True)
class ListingSnapshot:
    listing_id: int
    source_url: str
    search_title: str
    search_price_text: str
    search_area_text: str
    search_location_text: str
    detail_title: str
    detail_description: str
    contact_block: str
    published_at_text: str
    content_hash: str
    detail_attributes_text: str = ""
    detail_top_tab_text: str = ""
    detail_item_description: str = ""
    detail_agency_text: str = ""
    room_count_text: str = ""
    region_text: str = ""
    display_date_text: str = ""
    id: int | None = None
    captured_at: datetime | None = None


@dataclass(slots=True)
class ListingFeatures:
    listing_id: int
    bedroom_count_guess: int | None
    two_bedroom_match: str
    heating_text_raw: str
    heating_type_norm: str
    utilities_text_raw: str
    utilities_status: str
    location_match: bool
    feature_flags: dict[str, str] = field(default_factory=dict)
    reason_json: dict[str, object] = field(default_factory=dict)
    evaluated_at: datetime | None = None
