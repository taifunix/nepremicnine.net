# Raw Snapshots And Text Facts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist every seen listing with structured raw text snapshots and separately stored derived text facts for bedrooms, utilities, and heating.

**Architecture:** Keep the current `listings` table as the identity and price-tracking layer, add snapshot/history persistence for textual evidence, and split classification into two phases: fact extraction from snapshots and decision evaluation from facts. The polling runner changes so persistence happens for every processed listing before notification gating.

**Tech Stack:** Python 3.12, sqlite3, BeautifulSoup4, pytest, existing local package modules

---

## Planned File Structure

- `src/nepremicnine_bot/models.py`
  Add dataclasses for text snapshots and derived text facts.
- `src/nepremicnine_bot/parser.py`
  Add a snapshot builder that combines search-card and detail-page fields.
- `src/nepremicnine_bot/storage.py`
  Add tables and CRUD for `listing_snapshots` and `listing_features`.
- `src/nepremicnine_bot/classifier.py`
  Split into `extract_text_facts()` and `evaluate_listing_facts()`.
- `src/nepremicnine_bot/runner.py`
  Persist all seen listings, persist snapshots and features, and only then decide on notification.
- `tests/test_parser.py`
  Add snapshot-contract tests.
- `tests/test_storage.py`
  Add snapshot and feature persistence tests.
- `tests/test_classifier.py`
  Add extractor and evaluator tests for bedrooms, utilities, and heating.
- `tests/test_runner.py`
  Add regression coverage that filtered-out listings still enter the database.
- `README.md`
  Update the storage model and command behavior notes if the final implementation changes observable behavior.

### Task 1: Add snapshot and feature domain models

**Files:**
- Modify: `src/nepremicnine_bot/models.py`
- Modify: `tests/test_config.py`
- Test: `tests/test_config.py`

- [ ] **Step 1: Write the failing model test**

```python
from nepremicnine_bot.models import ListingFeatures, ListingSnapshot


def test_snapshot_and_feature_models_have_expected_defaults():
    snapshot = ListingSnapshot(
        listing_id=1,
        source_url="https://www.nepremicnine.net/oglasi-oddaja/test-1111111/",
        search_title="Stanovanje 2 spalnici",
        search_price_text="1.200 EUR/mesec",
        search_area_text="60 m2",
        search_location_text="Ljubljana Center",
        detail_title="Stanovanje 2 spalnici",
        detail_description="Centralno ogrevanje. Stroški vključeni.",
        contact_block="Kontaktni podatki ZASEBNA PONUDBA",
        published_at_text="danes",
        content_hash="abc123",
    )
    features = ListingFeatures(
        listing_id=1,
        bedroom_count_guess=2,
        two_bedroom_match="yes",
        heating_text_raw="Centralno ogrevanje",
        heating_type_norm="central",
        utilities_text_raw="Stroški vključeni",
        utilities_status="included_yes",
        location_match=True,
    )

    assert snapshot.id is None
    assert features.feature_flags == {}
    assert features.reason_json == {}
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_config.py::test_snapshot_and_feature_models_have_expected_defaults -v`
Expected: FAIL with `ImportError` or `AttributeError` for missing models.

- [ ] **Step 3: Write the minimal model implementation**

```python
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
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_config.py::test_snapshot_and_feature_models_have_expected_defaults -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/nepremicnine_bot/models.py tests/test_config.py
git commit -m "feat: add snapshot and feature models"
```

### Task 2: Build structured listing snapshots in the parser

**Files:**
- Modify: `src/nepremicnine_bot/parser.py`
- Modify: `tests/test_parser.py`
- Test: `tests/test_parser.py`

- [ ] **Step 1: Write the failing parser snapshot tests**

```python
from pathlib import Path

from nepremicnine_bot.parser import build_listing_snapshot, parse_listing_detail, parse_search_results


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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_parser.py::test_build_listing_snapshot_combines_search_and_detail_fields -v`
Expected: FAIL with missing `build_listing_snapshot`.

- [ ] **Step 3: Write the minimal parser implementation**

```python
from hashlib import sha1

from nepremicnine_bot.models import ListingSnapshot


def _normalize_snapshot_text(value: str) -> str:
    return " ".join(value.split())


def build_listing_snapshot(listing_id: int, search_result: dict[str, object], detail: dict[str, object]) -> ListingSnapshot:
    search_title = _normalize_snapshot_text(str(search_result.get("title", "")))
    search_price_text = _normalize_snapshot_text(str(search_result.get("price_text", "")))
    search_area_text = _normalize_snapshot_text(str(search_result.get("area_text", "")))
    search_location_text = _normalize_snapshot_text(str(search_result.get("location_text", "")))
    detail_title = _normalize_snapshot_text(str(detail.get("title", "")))
    detail_description = _normalize_snapshot_text(str(detail.get("description", "")))
    contact_block = _normalize_snapshot_text(str(detail.get("contact_block", "")))
    published_at_text = _normalize_snapshot_text(str(detail.get("published_at_text", "")))
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
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_parser.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/nepremicnine_bot/parser.py tests/test_parser.py
git commit -m "feat: add listing snapshot builder"
```

### Task 3: Persist snapshots and latest derived features in SQLite

**Files:**
- Modify: `src/nepremicnine_bot/storage.py`
- Modify: `tests/test_storage.py`
- Test: `tests/test_storage.py`

- [ ] **Step 1: Write the failing storage tests**

```python
from nepremicnine_bot.models import Listing, ListingFeatures, ListingSnapshot
from nepremicnine_bot.storage import Database


def test_snapshot_and_features_are_persisted(tmp_path):
    db = Database(tmp_path / "app.db")
    db.initialize()
    listing_id = db.upsert_listing(
        Listing(
            site_id="4444444",
            url="https://example.com/4444444",
            title="Candidate",
            price_current=1400,
            area=64.0,
            location_text="Center",
        )
    )
    snapshot_id = db.insert_listing_snapshot(
        ListingSnapshot(
            listing_id=listing_id,
            source_url="https://example.com/4444444",
            search_title="Candidate",
            search_price_text="1.400 EUR/mesec",
            search_area_text="64 m2",
            search_location_text="Center",
            detail_title="Candidate",
            detail_description="Centralno ogrevanje. Stroški vključeni.",
            contact_block="Kontaktni podatki ZASEBNA PONUDBA",
            published_at_text="danes",
            content_hash="hash-1",
        )
    )
    db.upsert_listing_features(
        ListingFeatures(
            listing_id=listing_id,
            bedroom_count_guess=2,
            two_bedroom_match="yes",
            heating_text_raw="Centralno ogrevanje",
            heating_type_norm="central",
            utilities_text_raw="Stroški vključeni",
            utilities_status="included_yes",
            location_match=True,
        )
    )

    snapshots = db.list_listing_snapshots(listing_id)
    features = db.get_listing_features(listing_id)

    assert snapshot_id == 1
    assert len(snapshots) == 1
    assert snapshots[0]["content_hash"] == "hash-1"
    assert features is not None
    assert features["heating_type_norm"] == "central"
    assert features["utilities_status"] == "included_yes"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_storage.py::test_snapshot_and_features_are_persisted -v`
Expected: FAIL with missing database methods or schema.

- [ ] **Step 3: Write the minimal schema and CRUD**

```python
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
```

```python
def insert_listing_snapshot(self, snapshot: ListingSnapshot) -> int:
    ...


def list_listing_snapshots(self, listing_id: int) -> list[dict[str, str]]:
    ...


def upsert_listing_features(self, features: ListingFeatures) -> None:
    ...


def get_listing_features(self, listing_id: int) -> dict[str, object] | None:
    ...
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_storage.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/nepremicnine_bot/storage.py tests/test_storage.py
git commit -m "feat: persist listing snapshots and features"
```

### Task 4: Split classification into text fact extraction and rule evaluation

**Files:**
- Modify: `src/nepremicnine_bot/classifier.py`
- Modify: `tests/test_classifier.py`
- Test: `tests/test_classifier.py`

- [ ] **Step 1: Write the failing classifier tests**

```python
from nepremicnine_bot.classifier import evaluate_listing_facts, extract_text_facts
from nepremicnine_bot.config import RuleSet
from nepremicnine_bot.models import ListingSnapshot


def test_extract_text_facts_detects_bedrooms_utilities_and_heating():
    snapshot = ListingSnapshot(
        listing_id=1,
        source_url="https://example.com/1",
        search_title="Stanovanje 2 spalnici",
        search_price_text="1.200 EUR/mesec",
        search_area_text="60 m2",
        search_location_text="Ljubljana Center",
        detail_title="Stanovanje 2 spalnici",
        detail_description="Centralno ogrevanje. Stroški vključeni.",
        contact_block="Kontaktni podatki ZASEBNA PONUDBA",
        published_at_text="danes",
        content_hash="hash-1",
    )

    features = extract_text_facts(snapshot, RuleSet(), ["siska"])

    assert features.bedroom_count_guess == 2
    assert features.two_bedroom_match == "yes"
    assert features.heating_type_norm == "central"
    assert features.utilities_status == "included_yes"
    assert features.location_match is True


def test_evaluate_listing_facts_marks_filtered_listing_without_notification():
    snapshot = ListingSnapshot(
        listing_id=1,
        source_url="https://example.com/1",
        search_title="Garsonjera",
        search_price_text="900 EUR/mesec",
        search_area_text="30 m2",
        search_location_text="Ljubljana Siska",
        detail_title="Garsonjera",
        detail_description="Električno ogrevanje. Stroški niso vključeni.",
        contact_block="Kontaktni podatki ZASEBNA PONUDBA",
        published_at_text="danes",
        content_hash="hash-2",
    )
    features = extract_text_facts(snapshot, RuleSet(), ["siska"])

    evaluation = evaluate_listing_facts(snapshot, features, RuleSet())

    assert evaluation.passes_realtime is False
    assert evaluation.reason_json["bedroom_match"] == "no"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_classifier.py -v`
Expected: FAIL with missing extraction/evaluation functions.

- [ ] **Step 3: Write the minimal extractor and evaluator**

```python
def extract_text_facts(snapshot: ListingSnapshot, rules, location_blacklist: list[str]) -> ListingFeatures:
    haystack = " ".join(
        [
            snapshot.search_title,
            snapshot.search_location_text,
            snapshot.detail_title,
            snapshot.detail_description,
            snapshot.contact_block,
        ]
    ).lower()
    location_text = snapshot.search_location_text.lower()

    bedroom_count_guess = 2 if any(term.lower() in haystack for term in rules.two_bedroom_positive) else None
    two_bedroom_match = "yes" if bedroom_count_guess == 2 else (
        "no" if any(term.lower() in haystack for term in rules.two_bedroom_negative) else "maybe"
    )
    if "centralno ogrevanje" in haystack:
        heating_text_raw = "centralno ogrevanje"
        heating_type_norm = "central"
    elif "elektri" in haystack:
        heating_text_raw = "električno ogrevanje"
        heating_type_norm = "electric"
    else:
        heating_text_raw = ""
        heating_type_norm = "unknown"
    if any(term.lower() in haystack for term in rules.utilities_included_positive):
        utilities_text_raw = snapshot.detail_description
        utilities_status = "included_yes"
    elif any(term.lower() in haystack for term in rules.utilities_included_partial):
        utilities_text_raw = snapshot.detail_description
        utilities_status = "partial"
    elif any(term.lower() in haystack for term in rules.utilities_separate_negative):
        utilities_text_raw = snapshot.detail_description
        utilities_status = "no"
    else:
        utilities_text_raw = snapshot.detail_description
        utilities_status = "unknown"
    location_match = not any(term.lower() in location_text for term in location_blacklist)
    return ListingFeatures(
        listing_id=snapshot.listing_id,
        bedroom_count_guess=bedroom_count_guess,
        two_bedroom_match=two_bedroom_match,
        heating_text_raw=heating_text_raw,
        heating_type_norm=heating_type_norm,
        utilities_text_raw=utilities_text_raw,
        utilities_status=utilities_status,
        location_match=location_match,
    )


def evaluate_listing_facts(snapshot: ListingSnapshot, features: ListingFeatures, rules) -> ListingEvaluation:
    is_private = "ZASEBNA PONUDBA" in snapshot.contact_block
    evaluation = ListingEvaluation(
        listing_id=snapshot.listing_id,
        is_private=is_private,
        is_agency=not is_private,
        two_bedroom_match=features.two_bedroom_match,
        utilities_status=features.utilities_status,
        location_match=features.location_match,
    )
    evaluation.feature_flags = dict(features.feature_flags)
    evaluation.passes_realtime = is_private and features.two_bedroom_match == "yes" and features.location_match
    evaluation.passes_daily_digest = (not is_private) and features.two_bedroom_match == "yes" and features.location_match
    evaluation.reason_json = {
        "bedroom_match": features.two_bedroom_match,
        "utilities_status": features.utilities_status,
        "heating_type_norm": features.heating_type_norm,
        "location_match": features.location_match,
    }
    return evaluation
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_classifier.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/nepremicnine_bot/classifier.py tests/test_classifier.py
git commit -m "feat: split text fact extraction from evaluation"
```

### Task 5: Persist all seen listings before filtering in the polling runner

**Files:**
- Modify: `src/nepremicnine_bot/runner.py`
- Modify: `tests/test_runner.py`
- Test: `tests/test_runner.py`

- [ ] **Step 1: Write the failing runner regression test**

```python

def test_poll_search_source_persists_filtered_out_listing_without_notifying(tmp_path):
    from nepremicnine_bot.config import RuleSet, SearchSource
    from nepremicnine_bot.storage import Database

    db = Database(tmp_path / "app.db")
    db.initialize()
    notifier = StubNotifier()
    fetcher = StubFetcher(
        {
            "https://search.example": """
            <html><body>
              <div data-ad-id='9999999'>
                <a href='https://detail.example/9999999'>Open</a>
                <div class='title'>Garsonjera</div>
                <div class='price'>900 EUR/mesec</div>
                <div class='area'>30 m2</div>
                <div class='location'>Ljubljana Siska</div>
              </div>
            </body></html>
            """,
            "https://detail.example/9999999": """
            <html><body>
              <h1>Garsonjera</h1>
              <div class='price'>900 EUR/mesec</div>
              <div class='area'>30 m2</div>
              <div class='location'>Ljubljana Siska</div>
              <div class='description'>Električno ogrevanje. Stroški niso vključeni.</div>
              <div id='kontaktni-podatki'>Kontaktni podatki ZASEBNA PONUDBA</div>
            </body></html>
            """,
        }
    )
    source = SearchSource(name="lj-center", url="https://search.example", location_blacklist=["siska"])

    sent = poll_search_source(source, fetcher, db, notifier, RuleSet())
    listing = db.get_listing_by_site_id("9999999")
    snapshots = db.list_listing_snapshots(listing.id)
    features = db.get_listing_features(listing.id)

    assert sent == 0
    assert notifier.messages == []
    assert listing is not None
    assert len(snapshots) == 1
    assert features is not None
    assert features["two_bedroom_match"] == "no"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/test_runner.py::test_poll_search_source_persists_filtered_out_listing_without_notifying -v`
Expected: FAIL because filtered-out listings are currently skipped before persistence.

- [ ] **Step 3: Write the minimal runner changes**

```python
from nepremicnine_bot.classifier import evaluate_listing_facts, extract_text_facts
from nepremicnine_bot.parser import build_listing_snapshot, parse_listing_detail, parse_search_results


def poll_search_source(source, fetcher, db, notifier, rules) -> int:
    sent = 0
    search_html = fetcher.fetch_text(source.url)
    results = parse_search_results(search_html)

    for result in results:
        detail_url = str(result["url"])
        detail_html = fetcher.fetch_text(detail_url)
        detail = parse_listing_detail(detail_html, detail_url)
        listing = Listing(
            site_id=str(detail["site_id"]),
            url=str(detail["url"]),
            title=str(detail["title"]),
            price_current=_parse_price_to_int(str(detail["price_text"])),
            area=_parse_area_to_float(str(detail["area_text"])),
            location_text=str(detail["location_text"]),
        )
        existing = db.get_listing_by_site_id(listing.site_id)
        listing_id = db.upsert_listing(listing)
        snapshot = build_listing_snapshot(listing_id=listing_id, search_result=result, detail=detail)
        db.insert_listing_snapshot(snapshot)
        features = extract_text_facts(snapshot, rules, source.location_blacklist)
        db.upsert_listing_features(features)
        evaluation = evaluate_listing_facts(snapshot, features, rules)

        event = process_listing_event(
            existing_price=existing.price_current if existing else None,
            new_price=listing.price_current,
            passes_realtime=evaluation.passes_realtime,
        )
        if existing and listing.price_current != existing.price_current:
            db.record_price(listing_id, listing.price_current)
        if event == "new_listing":
            ...
        elif event == "price_drop" and existing is not None:
            ...
    return sent
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `pytest tests/test_runner.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/nepremicnine_bot/runner.py tests/test_runner.py
git commit -m "feat: persist all listings before notification gating"
```

### Task 6: Update docs and do a final regression pass

**Files:**
- Modify: `README.md`
- Test: `tests/test_config.py`
- Test: `tests/test_parser.py`
- Test: `tests/test_storage.py`
- Test: `tests/test_classifier.py`
- Test: `tests/test_runner.py`
- Test: `tests/test_bot.py`
- Test: `tests/test_fetcher.py`

- [ ] **Step 1: Update README with the new storage model**

```md
## Data Retention Model

The polling pipeline stores every seen listing in SQLite, even if it does not pass realtime filters.

For each processed listing the service stores:
- a compact listing row for identity and price tracking
- a structured text snapshot from search and detail views
- the latest extracted text facts for bedrooms, utilities, heating, and future rule families

This allows rule tuning on a growing local corpus without re-fetching the site.
```

- [ ] **Step 2: Run the full test suite**

Run: `pytest -q`
Expected: PASS with all tests green.

- [ ] **Step 3: Commit**

```bash
git add README.md tests/test_config.py tests/test_parser.py tests/test_storage.py tests/test_classifier.py tests/test_runner.py tests/test_bot.py tests/test_fetcher.py
git commit -m "docs: describe snapshot and feature storage model"
```

## Self-Review

### Spec Coverage

- Save all seen listings: Task 5 persists all processed listings before filtering.
- Save structured raw text snapshots: Tasks 1-3 add the snapshot model, parser contract, and SQLite persistence.
- Save derived text facts separately: Tasks 1, 3, and 4 add the model, storage, and extraction/evaluation logic.
- Bedrooms/utilities/heating: Task 4 covers all three initial fact families.
- No raw HTML yet: no task introduces HTML archiving.
- Filtering after persistence: Task 5 changes runner sequencing accordingly.

### Placeholder Scan

Checked for `TBD`, `TODO`, vague “add error handling,” and “similar to previous task.” No intentional placeholders remain.

### Type Consistency

The plan consistently uses `ListingSnapshot`, `ListingFeatures`, `build_listing_snapshot()`, `extract_text_facts()`, `evaluate_listing_facts()`, `insert_listing_snapshot()`, `list_listing_snapshots()`, `upsert_listing_features()`, and `get_listing_features()` across tasks.
