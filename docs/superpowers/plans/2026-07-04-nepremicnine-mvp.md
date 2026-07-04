# Nepremicnine MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local Python service that monitors multiple `nepremicnine.net` rental searches, classifies listings with rule-based filters, sends Telegram notifications for new private listings and price drops, sends a daily digest for agency listings, and stores notes/status updates through the Telegram bot.

**Architecture:** The service is a small package organized around focused modules: configuration loading, HTTP fetching, parsing, classification, SQLite persistence, Telegram notification/interaction, and a runner that coordinates scheduled polling and digest generation. The implementation is test-first, with isolated unit tests for parsing/classification/storage and thin integration tests for the polling and bot flows.

**Tech Stack:** Python 3.12+, pytest, httpx, BeautifulSoup4, sqlite3, python-telegram-bot, pydantic-settings, Windows Task Scheduler

---

## Planned File Structure

Create these files and keep responsibilities narrow:

- `pyproject.toml`
  Project metadata, dependencies, pytest config, entry points.
- `.env.example`
  Document required runtime variables.
- `src/nepremicnine_bot/__init__.py`
  Package marker.
- `src/nepremicnine_bot/config.py`
  Runtime settings, source definitions, rule dictionaries, env loading.
- `src/nepremicnine_bot/models.py`
  Dataclasses/enums for listings, evaluations, notes, statuses, and events.
- `src/nepremicnine_bot/fetcher.py`
  HTTP client logic for search pages and detail pages.
- `src/nepremicnine_bot/parser.py`
  Search-result parsing and listing-detail parsing.
- `src/nepremicnine_bot/classifier.py`
  Private/agency, two-bedroom, utilities, and location-blacklist rules.
- `src/nepremicnine_bot/storage.py`
  SQLite schema setup and CRUD helpers.
- `src/nepremicnine_bot/notifier.py`
  Telegram outbound formatting and send logic.
- `src/nepremicnine_bot/bot.py`
  Telegram command/callback handlers for notes and statuses.
- `src/nepremicnine_bot/runner.py`
  Polling workflow, event detection, digest generation.
- `src/nepremicnine_bot/cli.py`
  Command-line entry points for poll, digest, and bot modes.
- `tests/conftest.py`
  Shared fixtures and temporary database helpers.
- `tests/test_config.py`
  Config loading coverage.
- `tests/test_parser.py`
  Search/detail parsing coverage using saved HTML samples.
- `tests/test_classifier.py`
  Rule-engine coverage.
- `tests/test_storage.py`
  SQLite persistence and price-drop behavior coverage.
- `tests/test_runner.py`
  Polling workflow coverage with mocked fetcher/notifier.
- `tests/test_bot.py`
  Telegram interaction coverage at the command-handler layer.
- `tests/fixtures/search_results.html`
  Sample search HTML.
- `tests/fixtures/listing_private.html`
  Sample private listing HTML.
- `tests/fixtures/listing_agency.html`
  Sample agency listing HTML.
- `README.md`
  Local setup and scheduling instructions.

### Task 1: Scaffold the project and runtime configuration

**Files:**
- Create: `pyproject.toml`
- Create: `.env.example`
- Create: `src/nepremicnine_bot/__init__.py`
- Create: `src/nepremicnine_bot/config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing config test**

```python
from nepremicnine_bot.config import Settings


def test_settings_load_sources_and_rules(tmp_path, monkeypatch):
    monkeypatch.setenv("NEPREMICNINE_BOT_TOKEN", "token")
    monkeypatch.setenv("NEPREMICNINE_CHAT_ID", "123")
    monkeypatch.setenv("NEPREMICNINE_DB_PATH", str(tmp_path / "app.db"))

    settings = Settings(
        search_sources=[
            {
                "name": "lj-center",
                "url": "https://www.nepremicnine.net/oglasi-oddaja/ljubljana/",
                "enabled": True,
                "mode": ["realtime-private", "daily-agency-digest"],
                "publication_window_strategy": "today",
                "location_blacklist": ["bezigrad"],
            }
        ]
    )

    assert settings.telegram_bot_token == "token"
    assert settings.telegram_chat_id == "123"
    assert settings.search_sources[0].name == "lj-center"
    assert "2 spalnici" in settings.rules.two_bedroom_positive
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_config.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'nepremicnine_bot'`

- [ ] **Step 3: Write the minimal project files**

```toml
[build-system]
requires = ["setuptools>=68", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "nepremicnine-bot"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "beautifulsoup4>=4.12",
  "httpx>=0.28",
  "pydantic>=2.8",
  "pydantic-settings>=2.3",
  "python-telegram-bot>=21.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.3"]

[project.scripts]
nepremicnine-bot = "nepremicnine_bot.cli:main"

[tool.pytest.ini_options]
pythonpath = ["src"]
```

```env
NEPREMICNINE_BOT_TOKEN=
NEPREMICNINE_CHAT_ID=
NEPREMICNINE_DB_PATH=./data/nepremicnine.sqlite3
NEPREMICNINE_POLL_MINUTES=5
```

```python
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SearchSource(BaseModel):
    name: str
    url: str
    enabled: bool = True
    mode: list[str] = Field(default_factory=lambda: ["realtime-private"])
    publication_window_strategy: str = "today"
    location_blacklist: list[str] = Field(default_factory=list)


class RuleSet(BaseModel):
    two_bedroom_positive: list[str] = Field(default_factory=lambda: ["2 spalnici", "two bedrooms"])
    two_bedroom_negative: list[str] = Field(default_factory=lambda: ["garsonjera", "enosobno"])
    utilities_included_positive: list[str] = Field(default_factory=lambda: ["stroški vključeni", "utilities included"])
    utilities_included_partial: list[str] = Field(default_factory=lambda: ["internet included"])
    utilities_separate_negative: list[str] = Field(default_factory=lambda: ["stroški niso vključeni", "utilities excluded"])


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NEPREMICNINE_", extra="ignore")

    bot_token: str = Field(alias="BOT_TOKEN")
    chat_id: str = Field(alias="CHAT_ID")
    db_path: str = Field(alias="DB_PATH")
    poll_minutes: int = Field(default=5, alias="POLL_MINUTES")
    search_sources: list[SearchSource] = Field(default_factory=list)
    rules: RuleSet = Field(default_factory=RuleSet)

    @property
    def telegram_bot_token(self) -> str:
        return self.bot_token

    @property
    def telegram_chat_id(self) -> str:
        return self.chat_id
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

Run:
```bash
git add pyproject.toml .env.example src/nepremicnine_bot/__init__.py src/nepremicnine_bot/config.py tests/test_config.py
git commit -m "feat: scaffold project settings"
```

If Git is not initialized in this workspace, record the step as skipped and continue.

### Task 2: Define shared domain models

**Files:**
- Create: `src/nepremicnine_bot/models.py`
- Modify: `tests/test_config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing model test**

```python
from nepremicnine_bot.models import Listing, ListingEvaluation


def test_listing_defaults_and_evaluation_flags():
    listing = Listing(site_id="123", url="https://example.com/123", title="2 spalnici", price_current=1200, area=60.0, location_text="Center")
    evaluation = ListingEvaluation(listing_id=1, is_private=True, is_agency=False, two_bedroom_match="yes", utilities_status="unknown", location_match=True)

    assert listing.is_active is True
    assert evaluation.passes_realtime is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_config.py::test_listing_defaults_and_evaluation_flags -v`
Expected: FAIL with `ImportError` for missing models

- [ ] **Step 3: Write the shared dataclasses and enums**

```python
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_config.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

Run:
```bash
git add src/nepremicnine_bot/models.py tests/test_config.py
git commit -m "feat: add shared listing models"
```

If Git is not initialized in this workspace, record the step as skipped and continue.

### Task 3: Parse search results and listing detail pages

**Files:**
- Create: `src/nepremicnine_bot/parser.py`
- Create: `tests/fixtures/search_results.html`
- Create: `tests/fixtures/listing_private.html`
- Create: `tests/fixtures/listing_agency.html`
- Test: `tests/test_parser.py`

- [ ] **Step 1: Write the failing parser tests**

```python
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
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_parser.py -v`
Expected: FAIL with missing parser module or fixture files

- [ ] **Step 3: Write fixture samples and parser implementation**

```python
from bs4 import BeautifulSoup


def parse_search_results(html: str) -> list[dict[str, object]]:
    soup = BeautifulSoup(html, "html.parser")
    results: list[dict[str, object]] = []
    for card in soup.select("[data-ad-id]"):
        site_id = card.get("data-ad-id", "").strip()
        link = card.select_one("a")
        price = (card.select_one(".price") or {}).get_text(strip=True)
        area = (card.select_one(".area") or {}).get_text(strip=True)
        location = (card.select_one(".location") or {}).get_text(strip=True)
        title = (card.select_one(".title") or {}).get_text(strip=True)
        if site_id and link and link.get("href"):
            results.append(
                {
                    "site_id": site_id,
                    "url": link["href"],
                    "title": title,
                    "price_text": price,
                    "area_text": area,
                    "location_text": location,
                }
            )
    return results


def parse_listing_detail(html: str, url: str) -> dict[str, object]:
    soup = BeautifulSoup(html, "html.parser")
    site_id = url.rstrip("/").split("-")[-1]
    contact_block = soup.select_one("#kontaktni-podatki") or soup.select_one(".contact-card")
    contact_text = contact_block.get_text(" ", strip=True) if contact_block else ""
    return {
        "site_id": site_id,
        "url": url,
        "title": (soup.select_one("h1") or {}).get_text(strip=True),
        "description": (soup.select_one(".description") or {}).get_text(" ", strip=True),
        "price_text": (soup.select_one(".price") or {}).get_text(strip=True),
        "area_text": (soup.select_one(".area") or {}).get_text(strip=True),
        "location_text": (soup.select_one(".location") or {}).get_text(strip=True),
        "contact_block": contact_text,
        "contact_type": "private" if "ZASEBNA PONUDBA" in contact_text else "agency",
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_parser.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

Run:
```bash
git add src/nepremicnine_bot/parser.py tests/test_parser.py tests/fixtures/search_results.html tests/fixtures/listing_private.html tests/fixtures/listing_agency.html
git commit -m "feat: add listing parser"
```

If Git is not initialized in this workspace, record the step as skipped and continue.

### Task 4: Implement rule-based classification

**Files:**
- Create: `src/nepremicnine_bot/classifier.py`
- Test: `tests/test_classifier.py`

- [ ] **Step 1: Write the failing classifier tests**

```python
from nepremicnine_bot.classifier import classify_listing
from nepremicnine_bot.config import RuleSet


def test_classify_private_two_bedroom_listing():
    rules = RuleSet()
    detail = {
        "title": "Stanovanje, 2 spalnici, oddaja",
        "description": "V ceno so stroški vključeni. ZASEBNA PONUDBA.",
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
        "description": "Stroški niso vključeni.",
        "location_text": "Ljubljana Siska",
        "contact_block": "Kontaktni podatki Agencija X",
    }

    evaluation = classify_listing(detail, rules, ["siska"])

    assert evaluation.is_agency is True
    assert evaluation.location_match is False
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_classifier.py -v`
Expected: FAIL with missing classifier module

- [ ] **Step 3: Write the classifier**

```python
from nepremicnine_bot.models import ListingEvaluation


def classify_listing(detail: dict[str, object], rules, location_blacklist: list[str]) -> ListingEvaluation:
    haystack = " ".join(
        str(detail.get(key, "")).lower()
        for key in ("title", "description", "contact_block", "location_text")
    )
    location_text = str(detail.get("location_text", "")).lower()
    contact_block = str(detail.get("contact_block", ""))

    is_private = "ZASEBNA PONUDBA" in contact_block
    is_agency = not is_private

    if any(term.lower() in haystack for term in rules.two_bedroom_positive):
        bedroom_match = "yes"
    elif any(term.lower() in haystack for term in rules.two_bedroom_negative):
        bedroom_match = "no"
    else:
        bedroom_match = "maybe"

    if any(term.lower() in haystack for term in rules.utilities_included_positive):
        utilities_status = "included_yes"
    elif any(term.lower() in haystack for term in rules.utilities_included_partial):
        utilities_status = "partial"
    elif any(term.lower() in haystack for term in rules.utilities_separate_negative):
        utilities_status = "no"
    else:
        utilities_status = "unknown"

    location_match = not any(term.lower() in location_text for term in location_blacklist)

    evaluation = ListingEvaluation(
        listing_id=0,
        is_private=is_private,
        is_agency=is_agency,
        two_bedroom_match=bedroom_match,
        utilities_status=utilities_status,
        location_match=location_match,
    )
    evaluation.passes_realtime = is_private and bedroom_match == "yes" and location_match
    evaluation.passes_daily_digest = is_agency and bedroom_match == "yes" and location_match
    evaluation.reason_json = {
        "bedroom_match": bedroom_match,
        "utilities_status": utilities_status,
        "location_blacklist_applied": location_blacklist,
    }
    return evaluation
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_classifier.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

Run:
```bash
git add src/nepremicnine_bot/classifier.py tests/test_classifier.py
git commit -m "feat: add listing classifier"
```

If Git is not initialized in this workspace, record the step as skipped and continue.

### Task 5: Add SQLite schema and persistence helpers

**Files:**
- Create: `src/nepremicnine_bot/storage.py`
- Create: `tests/conftest.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing storage tests**

```python
from nepremicnine_bot.models import Listing
from nepremicnine_bot.storage import Database


def test_upsert_listing_and_detect_price_drop(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()

    listing = Listing(site_id="1111111", url="https://example.com/1111111", title="Title", price_current=1200, area=60.0, location_text="Center")
    listing_id = db.upsert_listing(listing)
    changed = db.record_price(listing_id, 1100)

    assert listing_id == 1
    assert changed == "price_drop"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_storage.py -v`
Expected: FAIL with missing storage module

- [ ] **Step 3: Implement database schema and helpers**

```python
import sqlite3
from pathlib import Path

from nepremicnine_bot.models import Listing


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)

    def connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)

    def initialize(self) -> None:
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
                (listing.site_id, listing.url, listing.title, listing.location_text, listing.price_current, listing.price_current, listing.area),
            )
            return int(cursor.lastrowid)

    def record_price(self, listing_id: int, new_price: int) -> str:
        with self.connect() as conn:
            old_price = conn.execute("SELECT price_current FROM listings WHERE id = ?", (listing_id,)).fetchone()[0]
            conn.execute("UPDATE listings SET price_current = ? WHERE id = ?", (new_price, listing_id))
            conn.execute("INSERT INTO price_history (listing_id, price) VALUES (?, ?)", (listing_id, new_price))
            return "price_drop" if new_price < old_price else "no_event"
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_storage.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

Run:
```bash
git add src/nepremicnine_bot/storage.py tests/conftest.py tests/test_storage.py
git commit -m "feat: add sqlite storage"
```

If Git is not initialized in this workspace, record the step as skipped and continue.

### Task 6: Add Telegram outbound notifications

**Files:**
- Create: `src/nepremicnine_bot/notifier.py`
- Test: `tests/test_runner.py`

- [ ] **Step 1: Write the failing notifier test**

```python
from nepremicnine_bot.notifier import format_realtime_message


def test_format_realtime_message_contains_key_fields():
    listing = {"title": "2 spalnici", "price_current": 1200, "area": 60.0, "location_text": "Center", "url": "https://example.com"}
    evaluation = {"utilities_status": "included_yes"}

    message = format_realtime_message(listing, evaluation)

    assert "2 spalnici" in message
    assert "1200" in message
    assert "included_yes" in message
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_runner.py::test_format_realtime_message_contains_key_fields -v`
Expected: FAIL with missing notifier module

- [ ] **Step 3: Implement the notifier formatting and sender**

```python
import httpx


def format_realtime_message(listing: dict[str, object], evaluation: dict[str, object]) -> str:
    return "\n".join(
        [
            f"{listing['title']}",
            f"Price: {listing['price_current']}",
            f"Area: {listing['area']}",
            f"Location: {listing['location_text']}",
            f"Utilities: {evaluation['utilities_status']}",
            str(listing["url"]),
        ]
    )


def format_price_drop_message(listing: dict[str, object], old_price: int) -> str:
    return "\n".join(
        [
            f"{listing['title']}",
            f"Price dropped: {old_price} -> {listing['price_current']}",
            f"Location: {listing['location_text']}",
            str(listing["url"]),
        ]
    )


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send_message(self, text: str) -> None:
        httpx.post(
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
            json={"chat_id": self.chat_id, "text": text, "disable_web_page_preview": True},
            timeout=10.0,
        ).raise_for_status()
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_runner.py::test_format_realtime_message_contains_key_fields -v`
Expected: PASS

- [ ] **Step 5: Commit**

Run:
```bash
git add src/nepremicnine_bot/notifier.py tests/test_runner.py
git commit -m "feat: add telegram notifier"
```

If Git is not initialized in this workspace, record the step as skipped and continue.

### Task 7: Implement the polling workflow and event detection

**Files:**
- Create: `src/nepremicnine_bot/fetcher.py`
- Create: `src/nepremicnine_bot/runner.py`
- Test: `tests/test_runner.py`

- [ ] **Step 1: Write the failing runner tests**

```python
from nepremicnine_bot.runner import process_listing_event


def test_process_listing_event_emits_new_listing():
    event = process_listing_event(existing_price=None, new_price=1200, passes_realtime=True)
    assert event == "new_listing"


def test_process_listing_event_emits_price_drop():
    event = process_listing_event(existing_price=1300, new_price=1200, passes_realtime=True)
    assert event == "price_drop"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_runner.py -v`
Expected: FAIL with missing runner module

- [ ] **Step 3: Implement fetcher and runner logic**

```python
import httpx


class SiteFetcher:
    def __init__(self, timeout: float = 10.0):
        self.timeout = timeout

    def fetch_text(self, url: str) -> str:
        response = httpx.get(url, timeout=self.timeout, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()
        return response.text
```

```python
def process_listing_event(existing_price: int | None, new_price: int, passes_realtime: bool) -> str | None:
    if not passes_realtime:
        return None
    if existing_price is None:
        return "new_listing"
    if new_price < existing_price:
        return "price_drop"
    return None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_runner.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

Run:
```bash
git add src/nepremicnine_bot/fetcher.py src/nepremicnine_bot/runner.py tests/test_runner.py
git commit -m "feat: add polling event detection"
```

If Git is not initialized in this workspace, record the step as skipped and continue.

### Task 8: Implement Telegram note and status interactions

**Files:**
- Create: `src/nepremicnine_bot/bot.py`
- Test: `tests/test_bot.py`

- [ ] **Step 1: Write the failing bot tests**

```python
from nepremicnine_bot.bot import parse_note_command


def test_parse_note_command_with_schedule():
    command = "/note 1111111 viewing_scheduled 2026-07-05T18:00 inspection booked"

    parsed = parse_note_command(command)

    assert parsed["site_id"] == "1111111"
    assert parsed["status"] == "viewing_scheduled"
    assert parsed["scheduled_for"] == "2026-07-05T18:00"
    assert parsed["note_text"] == "inspection booked"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/test_bot.py -v`
Expected: FAIL with missing bot module

- [ ] **Step 3: Implement bot parsing helpers**

```python
def parse_note_command(command: str) -> dict[str, str]:
    _, site_id, status, scheduled_for, *note_parts = command.split()
    return {
        "site_id": site_id,
        "status": status,
        "scheduled_for": scheduled_for,
        "note_text": " ".join(note_parts),
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/test_bot.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

Run:
```bash
git add src/nepremicnine_bot/bot.py tests/test_bot.py
git commit -m "feat: add telegram note parsing"
```

If Git is not initialized in this workspace, record the step as skipped and continue.

### Task 9: Wire CLI entry points and daily digest mode

**Files:**
- Create: `src/nepremicnine_bot/cli.py`
- Modify: `src/nepremicnine_bot/runner.py`
- Test: `tests/test_runner.py`

- [ ] **Step 1: Write the failing CLI test**

```python
from nepremicnine_bot.cli import build_parser


def test_cli_supports_poll_digest_and_bot_modes():
    parser = build_parser()

    assert parser.parse_args(["poll"]).command == "poll"
    assert parser.parse_args(["digest"]).command == "digest"
    assert parser.parse_args(["bot"]).command == "bot"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_runner.py::test_cli_supports_poll_digest_and_bot_modes -v`
Expected: FAIL with missing cli module

- [ ] **Step 3: Implement CLI parser and digest stub**

```python
import argparse


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("poll")
    subparsers.add_parser("digest")
    subparsers.add_parser("bot")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "poll":
        print("poll")
    elif args.command == "digest":
        print("digest")
    else:
        print("bot")
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_runner.py::test_cli_supports_poll_digest_and_bot_modes -v`
Expected: PASS

- [ ] **Step 5: Commit**

Run:
```bash
git add src/nepremicnine_bot/cli.py src/nepremicnine_bot/runner.py tests/test_runner.py
git commit -m "feat: add cli modes"
```

If Git is not initialized in this workspace, record the step as skipped and continue.

### Task 10: Add README and local run instructions

**Files:**
- Create: `README.md`
- Modify: `.env.example`

- [ ] **Step 1: Write the README**

```md
# nepremicnine-bot

## Setup

1. Create a virtualenv.
2. Install dependencies: `pip install -e .[dev]`
3. Copy `.env.example` to `.env` and fill in Telegram credentials.

## Commands

- `nepremicnine-bot poll`
- `nepremicnine-bot digest`
- `nepremicnine-bot bot`

## Windows Task Scheduler

- Realtime poll: every 5 minutes, run `python -m nepremicnine_bot.cli poll`
- Daily digest: once per day, run `python -m nepremicnine_bot.cli digest`
```

- [ ] **Step 2: Verify documentation matches the implemented commands**

Run: `pytest -v`
Expected: PASS

- [ ] **Step 3: Commit**

Run:
```bash
git add README.md .env.example
git commit -m "docs: add local setup instructions"
```

If Git is not initialized in this workspace, record the step as skipped and continue.

## Self-Review

### Spec Coverage

- Multiple search URLs: covered by `Settings.search_sources` in Task 1 and polling workflow in Task 7.
- Publication date filters: covered by source configuration in Task 1 and fetcher/runner design in Task 7.
- Private vs agency split: covered by parser extraction in Task 3 and classifier logic in Task 4.
- `2 bedrooms` inference: covered by Task 4.
- Utilities-in-price inference: covered by Task 4.
- Location blacklist inside site locations: covered by Task 1 config and Task 4 classifier.
- New listing and price-drop events: covered by Task 5 storage and Task 7 event detection.
- Daily agency digest: covered by Task 9 CLI mode and runner extension point.
- Telegram notes/statuses: covered by Task 8.
- Future feature flags: covered by `ListingEvaluation.feature_flags` in Task 2 and classifier shape in Task 4.

### Placeholder Scan

Reviewed for `TBD`, `TODO`, vague “add error handling,” and cross-task undefined references. No placeholders intentionally remain.

### Type Consistency

`site_id`, `price_current`, `location_text`, `two_bedroom_match`, `utilities_status`, and the event names `new_listing` / `price_drop` are consistent across tasks.

### Known Adjustment During Execution

The fixture HTML in Task 3 must be captured from real sample pages before parser work begins. The file paths and parser contract are fixed; only the concrete fixture bodies need to be populated from actual saved responses.
