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
