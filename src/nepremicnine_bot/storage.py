import json
import sqlite3
from pathlib import Path

from nepremicnine_bot.models import Listing, ListingEvaluation, ListingFeatures, ListingSnapshot


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS listings (
                    id INTEGER PRIMARY KEY,
                    site_id TEXT UNIQUE NOT NULL,
                    canonical_url TEXT NOT NULL,
                    title TEXT NOT NULL,
                    location_text TEXT NOT NULL,
                    price_current INTEGER NOT NULL,
                    price_first_seen INTEGER NOT NULL,
                    price_last_notified INTEGER,
                    area REAL NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1
                );
                CREATE TABLE IF NOT EXISTS price_history (
                    id INTEGER PRIMARY KEY,
                    listing_id INTEGER NOT NULL,
                    previous_price INTEGER,
                    price INTEGER NOT NULL,
                    observed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS listing_notes (
                    id INTEGER PRIMARY KEY,
                    listing_id INTEGER NOT NULL,
                    note_type TEXT NOT NULL,
                    note_text TEXT NOT NULL,
                    scheduled_for TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    created_via TEXT NOT NULL DEFAULT 'telegram'
                );
                CREATE TABLE IF NOT EXISTS listing_status (
                    listing_id INTEGER PRIMARY KEY,
                    status TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS listing_snapshots (
                    id INTEGER PRIMARY KEY,
                    listing_id INTEGER NOT NULL,
                    source_url TEXT NOT NULL,
                    search_title TEXT NOT NULL,
                    search_price_text TEXT NOT NULL,
                    search_area_text TEXT NOT NULL,
                    search_location_text TEXT NOT NULL,
                    detail_title TEXT NOT NULL,
                    detail_description TEXT NOT NULL,
                    contact_block TEXT NOT NULL,
                    published_at_text TEXT NOT NULL,
                    content_hash TEXT NOT NULL,
                    detail_attributes_text TEXT NOT NULL DEFAULT '',
                    detail_top_tab_text TEXT NOT NULL DEFAULT '',
                    detail_item_description TEXT NOT NULL DEFAULT '',
                    detail_agency_text TEXT NOT NULL DEFAULT '',
                    room_count_text TEXT NOT NULL DEFAULT '',
                    region_text TEXT NOT NULL DEFAULT '',
                    display_date_text TEXT NOT NULL DEFAULT '',
                    captured_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS listing_features (
                    listing_id INTEGER PRIMARY KEY,
                    bedroom_count_guess INTEGER,
                    two_bedroom_match TEXT NOT NULL,
                    heating_text_raw TEXT NOT NULL,
                    heating_type_norm TEXT NOT NULL,
                    utilities_text_raw TEXT NOT NULL,
                    utilities_status TEXT NOT NULL,
                    location_match INTEGER NOT NULL,
                    feature_flags_json TEXT NOT NULL,
                    reason_json TEXT NOT NULL,
                    evaluated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS listing_evaluations (
                    listing_id INTEGER PRIMARY KEY,
                    is_private INTEGER NOT NULL,
                    is_agency INTEGER NOT NULL,
                    two_bedroom_match TEXT NOT NULL,
                    utilities_status TEXT NOT NULL,
                    location_match INTEGER NOT NULL,
                    feature_flags_json TEXT NOT NULL,
                    passes_realtime INTEGER NOT NULL,
                    passes_daily_digest INTEGER NOT NULL,
                    reason_json TEXT NOT NULL,
                    evaluated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS telegram_message_mappings (
                    id INTEGER PRIMARY KEY,
                    chat_id TEXT NOT NULL,
                    telegram_message_id INTEGER NOT NULL,
                    listing_id INTEGER NOT NULL,
                    message_kind TEXT NOT NULL,
                    delete_after_at TEXT NOT NULL,
                    deleted_at TEXT,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    UNIQUE(chat_id, telegram_message_id)
                );
                CREATE TABLE IF NOT EXISTS chat_settings (
                    chat_id TEXT PRIMARY KEY,
                    price_min INTEGER,
                    price_max INTEGER,
                    area_min REAL,
                    area_max REAL,
                    bedrooms_min INTEGER,
                    bedrooms_max INTEGER,
                    include_maybe INTEGER NOT NULL DEFAULT 1,
                    seller_type TEXT NOT NULL DEFAULT 'all',
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS chat_input_state (
                    chat_id TEXT PRIMARY KEY,
                    state TEXT NOT NULL,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS audit_recovery_failures (
                    site_id TEXT PRIMARY KEY,
                    source_name TEXT NOT NULL,
                    detail_url TEXT NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL,
                    first_failed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    last_failed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    alert_sent_at TEXT
                );
                """
            )
            self._ensure_listing_snapshot_columns(conn)
            self._ensure_telegram_message_mapping_columns(conn)
            self._ensure_chat_settings_columns(conn)
            self._ensure_price_history_columns(conn)

    def record_audit_recovery_failure(
        self,
        *,
        site_id: str,
        source_name: str,
        detail_url: str,
        error_message: str,
    ) -> dict[str, object]:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO audit_recovery_failures (
                    site_id,
                    source_name,
                    detail_url,
                    attempts,
                    last_error
                )
                VALUES (?, ?, ?, 1, ?)
                ON CONFLICT(site_id) DO UPDATE SET
                    source_name = excluded.source_name,
                    detail_url = excluded.detail_url,
                    attempts = attempts + 1,
                    last_error = excluded.last_error,
                    last_failed_at = CURRENT_TIMESTAMP
                """,
                (site_id, source_name, detail_url, error_message),
            )
            row = conn.execute(
                """
                SELECT site_id, source_name, detail_url, attempts, last_error, alert_sent_at
                FROM audit_recovery_failures
                WHERE site_id = ?
                """,
                (site_id,),
            ).fetchone()
        return {
            "site_id": str(row[0]),
            "source_name": str(row[1]),
            "detail_url": str(row[2]),
            "attempts": int(row[3]),
            "last_error": str(row[4]),
            "alert_sent_at": row[5],
        }

    def clear_audit_recovery_failure(self, site_id: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM audit_recovery_failures WHERE site_id = ?", (site_id,))

    def mark_audit_recovery_alert_sent(self, site_id: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE audit_recovery_failures
                SET alert_sent_at = CURRENT_TIMESTAMP
                WHERE site_id = ?
                """,
                (site_id,),
            )

    def _ensure_listing_snapshot_columns(self, conn: sqlite3.Connection) -> None:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(listing_snapshots)").fetchall()}
        for column in (
            "detail_attributes_text",
            "detail_top_tab_text",
            "detail_item_description",
            "detail_agency_text",
            "room_count_text",
            "region_text",
            "display_date_text",
        ):
            if column not in columns:
                conn.execute(f"ALTER TABLE listing_snapshots ADD COLUMN {column} TEXT NOT NULL DEFAULT ''")

    def _ensure_telegram_message_mapping_columns(self, conn: sqlite3.Connection) -> None:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(telegram_message_mappings)").fetchall()}
        if not columns:
            return
        if "deleted_at" not in columns:
            conn.execute("ALTER TABLE telegram_message_mappings ADD COLUMN deleted_at TEXT")
        if "created_at" not in columns:
            conn.execute("ALTER TABLE telegram_message_mappings ADD COLUMN created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP")

    def _ensure_chat_settings_columns(self, conn: sqlite3.Connection) -> None:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(chat_settings)").fetchall()}
        if not columns:
            return
        if "seller_type" not in columns:
            conn.execute("ALTER TABLE chat_settings ADD COLUMN seller_type TEXT NOT NULL DEFAULT 'all'")

    def _ensure_price_history_columns(self, conn: sqlite3.Connection) -> None:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(price_history)").fetchall()}
        if not columns:
            return
        if "previous_price" not in columns:
            conn.execute("ALTER TABLE price_history ADD COLUMN previous_price INTEGER")

    def upsert_listing(self, listing: Listing) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT id FROM listings WHERE site_id = ?", (listing.site_id,)).fetchone()
            if row:
                conn.execute(
                    "UPDATE listings SET title=?, canonical_url=?, location_text=?, area=? WHERE id=?",
                    (listing.title, listing.url, listing.location_text, listing.area, row[0]),
                )
                return int(row[0])
            cursor = conn.execute(
                """
                INSERT INTO listings (site_id, canonical_url, title, location_text, price_current, price_first_seen, area)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    listing.site_id,
                    listing.url,
                    listing.title,
                    listing.location_text,
                    listing.price_current,
                    listing.price_current,
                    listing.area,
                ),
            )
            return int(cursor.lastrowid)

    def get_listing_by_site_id(self, site_id: str) -> Listing | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT id, site_id, canonical_url, title, price_current, area, location_text
                FROM listings
                WHERE site_id = ?
                """,
                (site_id,),
            ).fetchone()
        if row is None:
            return None
        return Listing(
            id=int(row[0]),
            site_id=str(row[1]),
            url=str(row[2]),
            title=str(row[3]),
            price_current=int(row[4]),
            area=float(row[5]),
            location_text=str(row[6]),
        )

    def list_listing_site_ids(self) -> set[str]:
        with self.connect() as conn:
            rows = conn.execute("SELECT site_id FROM listings").fetchall()
        return {str(row[0]) for row in rows}

    def record_price(self, listing_id: int, new_price: int) -> str:
        with self.connect() as conn:
            row = conn.execute("SELECT price_current FROM listings WHERE id = ?", (listing_id,)).fetchone()
            if row is None:
                raise ValueError(f"Unknown listing_id: {listing_id}")
            old_price = int(row[0])
            if new_price == old_price:
                return "no_event"
            conn.execute("UPDATE listings SET price_current = ? WHERE id = ?", (new_price, listing_id))
            conn.execute(
                "INSERT INTO price_history (listing_id, previous_price, price) VALUES (?, ?, ?)",
                (listing_id, old_price, new_price),
            )
            return "price_drop" if new_price < old_price else "price_rise"

    def get_latest_snapshot_metadata(self, listing_id: int) -> dict[str, object] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT id, content_hash, captured_at
                FROM listing_snapshots
                WHERE listing_id = ?
                ORDER BY id DESC
                LIMIT 1
                """,
                (listing_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": int(row[0]),
            "content_hash": str(row[1]),
            "captured_at": str(row[2]),
        }

    def get_latest_price_change(self, listing_id: int) -> dict[str, object] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT previous_price, price, observed_at
                FROM price_history
                WHERE listing_id = ? AND previous_price IS NOT NULL
                ORDER BY id DESC
                LIMIT 1
                """,
                (listing_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "previous_price": int(row[0]),
            "price": int(row[1]),
            "observed_at": str(row[2]),
        }

    def insert_listing_snapshot(self, snapshot: ListingSnapshot) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO listing_snapshots (
                    listing_id,
                    source_url,
                    search_title,
                    search_price_text,
                    search_area_text,
                    search_location_text,
                    detail_title,
                    detail_description,
                    contact_block,
                    published_at_text,
                    content_hash,
                    detail_attributes_text,
                    detail_top_tab_text,
                    detail_item_description,
                    detail_agency_text,
                    room_count_text,
                    region_text,
                    display_date_text
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snapshot.listing_id,
                    snapshot.source_url,
                    snapshot.search_title,
                    snapshot.search_price_text,
                    snapshot.search_area_text,
                    snapshot.search_location_text,
                    snapshot.detail_title,
                    snapshot.detail_description,
                    snapshot.contact_block,
                    snapshot.published_at_text,
                    snapshot.content_hash,
                    snapshot.detail_attributes_text,
                    snapshot.detail_top_tab_text,
                    snapshot.detail_item_description,
                    snapshot.detail_agency_text,
                    snapshot.room_count_text,
                    snapshot.region_text,
                    snapshot.display_date_text,
                ),
            )
            return int(cursor.lastrowid)

    def list_listing_snapshots(self, listing_id: int) -> list[dict[str, str]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, source_url, search_title, search_price_text, search_area_text, search_location_text,
                       detail_title, detail_description, contact_block, published_at_text, content_hash,
                       detail_attributes_text, detail_top_tab_text, detail_item_description, detail_agency_text,
                       room_count_text, region_text, display_date_text, captured_at
                FROM listing_snapshots
                WHERE listing_id = ?
                ORDER BY id ASC
                """,
                (listing_id,),
            ).fetchall()
        return [
            {
                "id": str(row[0]),
                "source_url": str(row[1]),
                "search_title": str(row[2]),
                "search_price_text": str(row[3]),
                "search_area_text": str(row[4]),
                "search_location_text": str(row[5]),
                "detail_title": str(row[6]),
                "detail_description": str(row[7]),
                "contact_block": str(row[8]),
                "published_at_text": str(row[9]),
                "content_hash": str(row[10]),
                "detail_attributes_text": str(row[11]),
                "detail_top_tab_text": str(row[12]),
                "detail_item_description": str(row[13]),
                "detail_agency_text": str(row[14]),
                "room_count_text": str(row[15]),
                "region_text": str(row[16]),
                "display_date_text": str(row[17]),
                "captured_at": str(row[18]),
            }
            for row in rows
        ]

    def upsert_listing_features(self, features: ListingFeatures) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO listing_features (
                    listing_id,
                    bedroom_count_guess,
                    two_bedroom_match,
                    heating_text_raw,
                    heating_type_norm,
                    utilities_text_raw,
                    utilities_status,
                    location_match,
                    feature_flags_json,
                    reason_json,
                    evaluated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(listing_id) DO UPDATE SET
                    bedroom_count_guess = excluded.bedroom_count_guess,
                    two_bedroom_match = excluded.two_bedroom_match,
                    heating_text_raw = excluded.heating_text_raw,
                    heating_type_norm = excluded.heating_type_norm,
                    utilities_text_raw = excluded.utilities_text_raw,
                    utilities_status = excluded.utilities_status,
                    location_match = excluded.location_match,
                    feature_flags_json = excluded.feature_flags_json,
                    reason_json = excluded.reason_json,
                    evaluated_at = CURRENT_TIMESTAMP
                """,
                (
                    features.listing_id,
                    features.bedroom_count_guess,
                    features.two_bedroom_match,
                    features.heating_text_raw,
                    features.heating_type_norm,
                    features.utilities_text_raw,
                    features.utilities_status,
                    int(features.location_match),
                    json.dumps(features.feature_flags, ensure_ascii=False),
                    json.dumps(features.reason_json, ensure_ascii=False),
                ),
            )

    def get_listing_features(self, listing_id: int) -> dict[str, object] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT listing_id, bedroom_count_guess, two_bedroom_match, heating_text_raw, heating_type_norm,
                       utilities_text_raw, utilities_status, location_match, feature_flags_json, reason_json, evaluated_at
                FROM listing_features
                WHERE listing_id = ?
                """,
                (listing_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "listing_id": int(row[0]),
            "bedroom_count_guess": int(row[1]) if row[1] is not None else None,
            "two_bedroom_match": str(row[2]),
            "heating_text_raw": str(row[3]),
            "heating_type_norm": str(row[4]),
            "utilities_text_raw": str(row[5]),
            "utilities_status": str(row[6]),
            "location_match": bool(row[7]),
            "feature_flags": json.loads(row[8]),
            "reason_json": json.loads(row[9]),
            "evaluated_at": str(row[10]),
        }

    def upsert_listing_evaluation(self, evaluation: ListingEvaluation) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO listing_evaluations (
                    listing_id,
                    is_private,
                    is_agency,
                    two_bedroom_match,
                    utilities_status,
                    location_match,
                    feature_flags_json,
                    passes_realtime,
                    passes_daily_digest,
                    reason_json,
                    evaluated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(listing_id) DO UPDATE SET
                    is_private = excluded.is_private,
                    is_agency = excluded.is_agency,
                    two_bedroom_match = excluded.two_bedroom_match,
                    utilities_status = excluded.utilities_status,
                    location_match = excluded.location_match,
                    feature_flags_json = excluded.feature_flags_json,
                    passes_realtime = excluded.passes_realtime,
                    passes_daily_digest = excluded.passes_daily_digest,
                    reason_json = excluded.reason_json,
                    evaluated_at = CURRENT_TIMESTAMP
                """,
                (
                    evaluation.listing_id,
                    int(evaluation.is_private),
                    int(evaluation.is_agency),
                    evaluation.two_bedroom_match,
                    evaluation.utilities_status,
                    int(evaluation.location_match),
                    json.dumps(evaluation.feature_flags, ensure_ascii=False),
                    int(evaluation.passes_realtime),
                    int(evaluation.passes_daily_digest),
                    json.dumps(evaluation.reason_json, ensure_ascii=False),
                ),
            )

    def get_listing_evaluation(self, listing_id: int) -> dict[str, object] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT listing_id, is_private, is_agency, two_bedroom_match, utilities_status, location_match,
                       feature_flags_json, passes_realtime, passes_daily_digest, reason_json, evaluated_at
                FROM listing_evaluations
                WHERE listing_id = ?
                """,
                (listing_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "listing_id": int(row[0]),
            "is_private": bool(row[1]),
            "is_agency": bool(row[2]),
            "two_bedroom_match": str(row[3]),
            "utilities_status": str(row[4]),
            "location_match": bool(row[5]),
            "feature_flags": json.loads(row[6]),
            "passes_realtime": bool(row[7]),
            "passes_daily_digest": bool(row[8]),
            "reason_json": json.loads(row[9]),
            "evaluated_at": str(row[10]),
        }

    def get_listing_summary_by_site_id(self, site_id: str) -> dict[str, object] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT l.id, l.site_id, l.canonical_url, l.title, l.price_current, l.area, l.location_text,
                       COALESCE(ls.status, 'new') AS status,
                       COALESCE(lf.bedroom_count_guess, NULL),
                       COALESCE(lf.heating_type_norm, 'unknown'),
                       COALESCE(lf.utilities_status, 'unknown'),
                       COALESCE(le.is_private, 0),
                       COALESCE(le.is_agency, 0),
                       COALESCE(le.two_bedroom_match, 'unknown'),
                       COALESCE(le.passes_realtime, 0),
                       COALESCE(le.passes_daily_digest, 0),
                       COALESCE(latest_snapshot.region_text, ''),
                       COALESCE(latest_snapshot.room_count_text, ''),
                       COALESCE(latest_snapshot.display_date_text, ''),
                       COALESCE(latest_snapshot.published_at_text, ''),
                       COALESCE(latest_snapshot.detail_attributes_text, ''),
                       COALESCE(latest_snapshot.detail_top_tab_text, ''),
                       COALESCE(latest_snapshot.detail_item_description, ''),
                       COALESCE(latest_snapshot.detail_description, ''),
                       COALESCE(latest_snapshot.captured_at, ''),
                       latest_price.previous_price,
                       latest_price.price,
                       COALESCE(latest_price.observed_at, '')
                FROM listings l
                LEFT JOIN listing_status ls ON ls.listing_id = l.id
                LEFT JOIN listing_features lf ON lf.listing_id = l.id
                LEFT JOIN listing_evaluations le ON le.listing_id = l.id
                LEFT JOIN listing_snapshots latest_snapshot ON latest_snapshot.id = (
                    SELECT ls2.id
                    FROM listing_snapshots ls2
                    WHERE ls2.listing_id = l.id
                    ORDER BY ls2.id DESC
                    LIMIT 1
                )
                LEFT JOIN price_history latest_price ON latest_price.id = (
                    SELECT ph2.id
                    FROM price_history ph2
                    WHERE ph2.listing_id = l.id AND ph2.previous_price IS NOT NULL
                    ORDER BY ph2.id DESC
                    LIMIT 1
                )
                WHERE l.site_id = ?
                """,
                (site_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "listing_id": int(row[0]),
            "site_id": str(row[1]),
            "url": str(row[2]),
            "title": str(row[3]),
            "price_current": int(row[4]),
            "area": float(row[5]),
            "location_text": str(row[6]),
            "status": str(row[7]),
            "bedroom_count_guess": int(row[8]) if row[8] is not None else None,
            "heating_type_norm": str(row[9]),
            "utilities_status": str(row[10]),
            "is_private": bool(row[11]),
            "is_agency": bool(row[12]),
            "two_bedroom_match": str(row[13]),
            "passes_realtime": bool(row[14]),
            "passes_daily_digest": bool(row[15]),
            "region_text": str(row[16]),
            "room_count_text": str(row[17]),
            "display_date_text": str(row[18]),
            "published_at_text": str(row[19]),
            "detail_attributes_text": str(row[20]),
            "detail_top_tab_text": str(row[21]),
            "detail_item_description": str(row[22]),
            "detail_description": str(row[23]),
            "captured_at": str(row[24]),
            "previous_price": int(row[25]) if row[25] is not None else None,
            "price_change_current": int(row[26]) if row[26] is not None else None,
            "price_change_observed_at": str(row[27]),
        }

    def list_recent_listing_candidates(self, *, limit: int, mode: str) -> list[dict[str, object]]:
        if mode == "new":
            where_clause = "(le.passes_realtime = 1 OR le.two_bedroom_match = 'maybe') AND COALESCE(ls.status, 'new') NOT IN ('saved', 'rejected', 'expensive')"
        elif mode == "saved":
            where_clause = "COALESCE(ls.status, 'new') = 'saved'"
        elif mode == "expensive":
            where_clause = "COALESCE(ls.status, 'new') = 'expensive'"
        elif mode == "realtime":
            where_clause = "le.passes_realtime = 1"
        else:
            where_clause = "le.two_bedroom_match = 'maybe'"
        with self.connect() as conn:
            rows = conn.execute(
                f"""
                SELECT l.id, l.site_id, l.title, l.canonical_url, l.price_current, l.area, l.location_text,
                       COALESCE(ls.status, 'new') AS status,
                       COALESCE(lf.utilities_status, 'unknown') AS utilities_status,
                       COALESCE(lf.heating_type_norm, 'unknown') AS heating_type_norm,
                       COALESCE(le.two_bedroom_match, 'unknown') AS two_bedroom_match,
                       COALESCE(le.passes_realtime, 0) AS passes_realtime,
                       COALESCE(le.passes_daily_digest, 0) AS passes_daily_digest,
                       COALESCE(le.is_private, 0) AS is_private,
                       COALESCE(le.is_agency, 0) AS is_agency,
                       COALESCE(latest_snapshot.region_text, '') AS region_text,
                       COALESCE(latest_snapshot.room_count_text, '') AS room_count_text,
                       COALESCE(latest_snapshot.display_date_text, '') AS display_date_text,
                       COALESCE(latest_snapshot.published_at_text, '') AS published_at_text,
                       COALESCE(latest_snapshot.detail_attributes_text, '') AS detail_attributes_text,
                       COALESCE(latest_snapshot.detail_top_tab_text, '') AS detail_top_tab_text,
                       COALESCE(latest_snapshot.detail_item_description, '') AS detail_item_description,
                       COALESCE(latest_snapshot.detail_description, '') AS detail_description,
                       COALESCE(latest_snapshot.captured_at, '') AS captured_at,
                       latest_price.previous_price,
                       latest_price.price,
                       COALESCE(latest_price.observed_at, '') AS price_change_observed_at
                FROM listings l
                JOIN listing_evaluations le ON le.listing_id = l.id
                LEFT JOIN listing_features lf ON lf.listing_id = l.id
                LEFT JOIN listing_status ls ON ls.listing_id = l.id
                LEFT JOIN listing_snapshots latest_snapshot ON latest_snapshot.id = (
                    SELECT ls2.id
                    FROM listing_snapshots ls2
                    WHERE ls2.listing_id = l.id
                    ORDER BY ls2.id DESC
                    LIMIT 1
                )
                LEFT JOIN price_history latest_price ON latest_price.id = (
                    SELECT ph2.id
                    FROM price_history ph2
                    WHERE ph2.listing_id = l.id AND ph2.previous_price IS NOT NULL
                    ORDER BY ph2.id DESC
                    LIMIT 1
                )
                WHERE {where_clause}
                ORDER BY COALESCE(latest_snapshot.id, 0) DESC, l.id DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "listing_id": int(row[0]),
                "site_id": str(row[1]),
                "title": str(row[2]),
                "url": str(row[3]),
                "price_current": int(row[4]),
                "area": float(row[5]),
                "location_text": str(row[6]),
                "status": str(row[7]),
                "utilities_status": str(row[8]),
                "heating_type_norm": str(row[9]),
                "two_bedroom_match": str(row[10]),
                "passes_realtime": bool(row[11]),
                "passes_daily_digest": bool(row[12]),
                "is_private": bool(row[13]),
                "is_agency": bool(row[14]),
                "region_text": str(row[15]),
                "room_count_text": str(row[16]),
                "display_date_text": str(row[17]),
                "published_at_text": str(row[18]),
                "detail_attributes_text": str(row[19]),
                "detail_top_tab_text": str(row[20]),
                "detail_item_description": str(row[21]),
                "detail_description": str(row[22]),
                "captured_at": str(row[23]),
                "previous_price": int(row[24]) if row[24] is not None else None,
                "price_change_current": int(row[25]) if row[25] is not None else None,
                "price_change_observed_at": str(row[26]),
            }
            for row in rows
        ]

    def set_listing_status(self, listing_id: int, status: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO listing_status (listing_id, status, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(listing_id) DO UPDATE SET
                    status = excluded.status,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (listing_id, status),
            )

    def get_listing_status(self, listing_id: int) -> dict[str, str] | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT listing_id, status, updated_at FROM listing_status WHERE listing_id = ?",
                (listing_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "listing_id": str(row[0]),
            "status": str(row[1]),
            "updated_at": str(row[2]),
        }

    def add_listing_note(
        self,
        listing_id: int,
        note_type: str,
        note_text: str,
        scheduled_for: str | None,
        *,
        created_via: str = "telegram",
    ) -> int:
        with self.connect() as conn:
            cursor = conn.execute(
                """
                INSERT INTO listing_notes (listing_id, note_type, note_text, scheduled_for, created_via)
                VALUES (?, ?, ?, ?, ?)
                """,
                (listing_id, note_type, note_text, scheduled_for, created_via),
            )
            return int(cursor.lastrowid)

    def list_listing_notes(self, listing_id: int) -> list[dict[str, str | None]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT id, note_type, note_text, scheduled_for, created_at, created_via
                FROM listing_notes
                WHERE listing_id = ?
                ORDER BY id ASC
                """,
                (listing_id,),
            ).fetchall()
        return [
            {
                "id": str(row[0]),
                "note_type": str(row[1]),
                "note_text": str(row[2]),
                "scheduled_for": str(row[3]) if row[3] is not None else None,
                "created_at": str(row[4]),
                "created_via": str(row[5]),
            }
            for row in rows
        ]

    def add_telegram_message_mapping(
        self,
        chat_id: str,
        telegram_message_id: int,
        listing_id: int,
        message_kind: str,
        delete_after_at: str,
    ) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO telegram_message_mappings (
                    chat_id,
                    telegram_message_id,
                    listing_id,
                    message_kind,
                    delete_after_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(chat_id, telegram_message_id) DO UPDATE SET
                    listing_id = excluded.listing_id,
                    message_kind = excluded.message_kind,
                    delete_after_at = excluded.delete_after_at,
                    deleted_at = NULL
                """,
                (chat_id, telegram_message_id, listing_id, message_kind, delete_after_at),
            )

    def get_listing_by_message(self, chat_id: str, telegram_message_id: int) -> dict[str, object] | None:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT listing_id, chat_id, telegram_message_id, message_kind, delete_after_at, deleted_at
                FROM telegram_message_mappings
                WHERE chat_id = ? AND telegram_message_id = ?
                """,
                (chat_id, telegram_message_id),
            ).fetchone()
        if row is None:
            return None
        return {
            "listing_id": int(row[0]),
            "chat_id": str(row[1]),
            "telegram_message_id": int(row[2]),
            "message_kind": str(row[3]),
            "delete_after_at": str(row[4]),
            "deleted_at": str(row[5]) if row[5] is not None else None,
        }

    def mark_telegram_message_deleted(self, chat_id: str, telegram_message_id: int) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                UPDATE telegram_message_mappings
                SET deleted_at = CURRENT_TIMESTAMP
                WHERE chat_id = ? AND telegram_message_id = ?
                """,
                (chat_id, telegram_message_id),
            )

    def list_expired_telegram_message_mappings(self, *, now_iso: str) -> list[dict[str, object]]:
        with self.connect() as conn:
            rows = conn.execute(
                """
                SELECT chat_id, telegram_message_id, listing_id, message_kind, delete_after_at
                FROM telegram_message_mappings
                WHERE deleted_at IS NULL AND delete_after_at <= ?
                ORDER BY id ASC
                """,
                (now_iso,),
            ).fetchall()
        return [
            {
                "chat_id": str(row[0]),
                "telegram_message_id": int(row[1]),
                "listing_id": int(row[2]),
                "message_kind": str(row[3]),
                "delete_after_at": str(row[4]),
            }
            for row in rows
        ]


    def get_chat_settings(self, chat_id: str) -> dict[str, object]:
        with self.connect() as conn:
            row = conn.execute(
                """
                SELECT price_min, price_max, area_min, area_max, bedrooms_min, bedrooms_max, include_maybe, seller_type
                FROM chat_settings
                WHERE chat_id = ?
                """,
                (chat_id,),
            ).fetchone()
        if row is None:
            return {
                "price_min": None,
                "price_max": None,
                "area_min": None,
                "area_max": None,
                "bedrooms_min": None,
                "bedrooms_max": None,
                "include_maybe": True,
                "seller_type": "all",
            }
        return {
            "price_min": int(row[0]) if row[0] is not None else None,
            "price_max": int(row[1]) if row[1] is not None else None,
            "area_min": float(row[2]) if row[2] is not None else None,
            "area_max": float(row[3]) if row[3] is not None else None,
            "bedrooms_min": int(row[4]) if row[4] is not None else None,
            "bedrooms_max": int(row[5]) if row[5] is not None else None,
            "include_maybe": bool(row[6]),
            "seller_type": str(row[7]) if row[7] else "all",
        }

    def upsert_chat_settings(self, chat_id: str, values: dict[str, object]) -> None:
        current = self.get_chat_settings(chat_id)
        merged = {**current, **values}
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_settings (
                    chat_id,
                    price_min,
                    price_max,
                    area_min,
                    area_max,
                    bedrooms_min,
                    bedrooms_max,
                    include_maybe,
                    seller_type,
                    updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(chat_id) DO UPDATE SET
                    price_min = excluded.price_min,
                    price_max = excluded.price_max,
                    area_min = excluded.area_min,
                    area_max = excluded.area_max,
                    bedrooms_min = excluded.bedrooms_min,
                    bedrooms_max = excluded.bedrooms_max,
                    include_maybe = excluded.include_maybe,
                    seller_type = excluded.seller_type,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    chat_id,
                    merged["price_min"],
                    merged["price_max"],
                    merged["area_min"],
                    merged["area_max"],
                    merged["bedrooms_min"],
                    merged["bedrooms_max"],
                    int(bool(merged["include_maybe"])),
                    str(merged["seller_type"] or "all"),
                ),
            )

    def get_chat_input_state(self, chat_id: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute("SELECT state FROM chat_input_state WHERE chat_id = ?", (chat_id,)).fetchone()
        return str(row[0]) if row else None

    def set_chat_input_state(self, chat_id: str, state: str) -> None:
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO chat_input_state (chat_id, state, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(chat_id) DO UPDATE SET
                    state = excluded.state,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (chat_id, state),
            )

    def clear_chat_input_state(self, chat_id: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM chat_input_state WHERE chat_id = ?", (chat_id,))
