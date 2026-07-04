import sqlite3
from pathlib import Path

from nepremicnine_bot.models import Listing


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
                    price INTEGER NOT NULL,
                    observed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def upsert_listing(self, listing: Listing) -> int:
        with self.connect() as conn:
            row = conn.execute("SELECT id FROM listings WHERE site_id = ?", (listing.site_id,)).fetchone()
            if row:
                conn.execute(
                    "UPDATE listings SET title=?, canonical_url=?, location_text=?, price_current=?, area=? WHERE id=?",
                    (listing.title, listing.url, listing.location_text, listing.price_current, listing.area, row[0]),
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

    def record_price(self, listing_id: int, new_price: int) -> str:
        with self.connect() as conn:
            row = conn.execute("SELECT price_current FROM listings WHERE id = ?", (listing_id,)).fetchone()
            if row is None:
                raise ValueError(f"Unknown listing_id: {listing_id}")
            old_price = int(row[0])
            conn.execute("UPDATE listings SET price_current = ? WHERE id = ?", (new_price, listing_id))
            conn.execute("INSERT INTO price_history (listing_id, price) VALUES (?, ?)", (listing_id, new_price))
            return "price_drop" if new_price < old_price else "no_event"
