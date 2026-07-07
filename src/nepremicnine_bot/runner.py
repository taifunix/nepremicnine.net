import json
import re
from dataclasses import dataclass
from math import ceil
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from nepremicnine_bot.classifier import evaluate_listing_facts, extract_text_facts
from nepremicnine_bot.models import Listing, ListingEvaluation
from nepremicnine_bot.bot import render_listing_card
from nepremicnine_bot.parser import (
    build_listing_snapshot,
    parse_listing_detail,
    parse_search_pagination_links,
    parse_search_results,
    parse_search_total_items,
)


@dataclass(slots=True)
class PollSourceStats:
    source_name: str
    source_url: str
    pages_fetched: int = 0
    search_results: int = 0
    details_fetched: int = 0
    new_listings: int = 0
    price_drops: int = 0
    price_rises: int = 0
    snapshots_inserted: int = 0
    snapshots_skipped: int = 0
    notifications_sent: int = 0
    errors: int = 0
    error_message: str | None = None


@dataclass(slots=True)
class SearchAuditStats:
    source_name: str
    source_url: str
    pages_fetched: int = 0
    site_total: int | None = None
    parsed_unique_ids: int = 0
    in_db: int = 0
    missing_ids: list[str] | None = None
    missing_results: list[dict[str, object]] | None = None
    watched_missing_ids: list[str] | None = None
    errors: int = 0
    error_message: str | None = None


def _parse_price_to_int(price_text: str) -> int:
    match = re.search(r"\d[\d. ]*(?:,\d+)?", price_text)
    if not match:
        return 0
    value = match.group(0).strip()
    value = value.split(",", 1)[0]
    digits = re.sub(r"\D", "", value)
    return int(digits) if digits else 0



def _parse_area_to_float(area_text: str) -> float:
    match = re.search(r"\d+(?:[.,]\d+)?", area_text)
    if not match:
        return 0.0
    return float(match.group(0).replace(",", "."))



def _replace_query_param(url: str, name: str, value: int) -> str:
    parsed = urlsplit(url)
    query = [(key, query_value) for key, query_value in parse_qsl(parsed.query, keep_blank_values=True) if key != name]
    query.append((name, str(value)))
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(query, doseq=True), parsed.fragment))



def _replace_path_page(url: str, page_number: int) -> str:
    parsed = urlsplit(url)
    path = re.sub(r"/stran-\d+/?$", "/", parsed.path)
    if not path.endswith("/"):
        path = f"{path}/"
    path = f"{path}stran-{page_number}/"
    return urlunsplit((parsed.scheme, parsed.netloc, path, parsed.query, parsed.fragment))



def _page_url_candidates(url: str, page_number: int) -> list[str]:
    return [
        _replace_query_param(url, "stran", page_number),
        _replace_query_param(url, "page", page_number),
        _replace_path_page(url, page_number),
    ]



def _discover_fallback_pagination(
    source_url: str,
    fetcher,
    first_page_ids: set[str],
    max_pages: int,
) -> tuple[list[tuple[str, str | None, list[dict[str, object]] | None]], str | None]:
    for candidate_url in _page_url_candidates(source_url, 2):
        try:
            html = fetcher.fetch_text(candidate_url)
        except Exception:
            continue
        results = parse_search_results(html)
        result_ids = {str(item.get("site_id", "")).strip() for item in results if str(item.get("site_id", "")).strip()}
        if not result_ids or result_ids.issubset(first_page_ids):
            continue
        if "stran=" in candidate_url:
            strategy = "stran"
        elif "page=" in candidate_url:
            strategy = "page"
        else:
            strategy = "path"
        queue: list[tuple[str, str | None, list[dict[str, object]] | None]] = [(candidate_url, html, results)]
        for page_number in range(3, max_pages + 1):
            if strategy == "stran":
                page_url = _replace_query_param(source_url, "stran", page_number)
            elif strategy == "page":
                page_url = _replace_query_param(source_url, "page", page_number)
            else:
                page_url = _replace_path_page(source_url, page_number)
            queue.append((page_url, None, None))
        return queue, strategy
    return [], None



def _iterate_search_pages(source_url: str, fetcher):
    queue: list[tuple[str, str | None, list[dict[str, object]] | None]] = [(source_url, None, None)]
    seen_page_urls: set[str] = set()

    while queue:
        page_url, html, results = queue.pop(0)
        if page_url in seen_page_urls:
            continue
        seen_page_urls.add(page_url)

        if html is None or results is None:
            html = fetcher.fetch_text(page_url)
            results = parse_search_results(html)

        yield page_url, html, results

        next_urls = parse_search_pagination_links(html, page_url)
        for next_url in next_urls:
            if next_url not in seen_page_urls and all(next_url != queued_url for queued_url, _, _ in queue):
                queue.append((next_url, None, None))

        if page_url != source_url or next_urls or not results:
            continue

        total_items = parse_search_total_items(html)
        if not total_items or total_items <= len(results):
            continue

        first_page_ids = {str(item.get("site_id", "")).strip() for item in results if str(item.get("site_id", "")).strip()}
        max_pages = ceil(total_items / len(results))
        fallback_queue, _strategy = _discover_fallback_pagination(source_url, fetcher, first_page_ids, max_pages)
        for candidate in fallback_queue:
            candidate_url = candidate[0]
            if candidate_url not in seen_page_urls and all(candidate_url != queued_url for queued_url, _, _ in queue):
                queue.append(candidate)



def process_listing_event(existing_price: int | None, new_price: int, passes_realtime: bool) -> str | None:
    if not passes_realtime:
        return None
    if existing_price is None:
        return "new_listing"
    if new_price < existing_price:
        return "price_drop"
    if new_price > existing_price:
        return "price_rise"
    return None



def _build_listing(search_result: dict[str, object], detail: dict[str, object]) -> Listing:
    return Listing(
        site_id=str(search_result.get("site_id") or detail["site_id"]),
        url=str(detail["url"]),
        title=str(detail["title"]),
        price_current=_parse_price_to_int(str(detail["price_text"])),
        area=_parse_area_to_float(str(detail["area_text"])),
        location_text=str(detail["location_text"]),
    )



def _persist_listing_analysis(db, listing: Listing, search_result: dict[str, object], detail: dict[str, object], rules, location_blacklist: list[str]):
    existing = db.get_listing_by_site_id(listing.site_id)
    listing_id = db.upsert_listing(listing)
    snapshot = build_listing_snapshot(listing_id=listing_id, search_result=search_result, detail=detail)
    latest_snapshot = db.get_latest_snapshot_metadata(listing_id)
    if latest_snapshot and str(latest_snapshot["content_hash"]) == snapshot.content_hash:
        stored_evaluation = db.get_listing_evaluation(listing_id)
        if stored_evaluation is not None:
            return (
                existing,
                snapshot,
                None,
                ListingEvaluation(
                    listing_id=int(stored_evaluation["listing_id"]),
                    is_private=bool(stored_evaluation["is_private"]),
                    is_agency=bool(stored_evaluation["is_agency"]),
                    two_bedroom_match=str(stored_evaluation["two_bedroom_match"]),
                    utilities_status=str(stored_evaluation["utilities_status"]),
                    location_match=bool(stored_evaluation["location_match"]),
                    feature_flags=dict(stored_evaluation["feature_flags"]),
                    passes_realtime=bool(stored_evaluation["passes_realtime"]),
                    passes_daily_digest=bool(stored_evaluation["passes_daily_digest"]),
                    reason_json=dict(stored_evaluation["reason_json"]),
                ),
                False,
            )
    db.insert_listing_snapshot(snapshot)
    features = extract_text_facts(snapshot, rules, location_blacklist)
    db.upsert_listing_features(features)
    evaluation = evaluate_listing_facts(snapshot, features, rules)
    db.upsert_listing_evaluation(evaluation)
    return existing, snapshot, features, evaluation, True



def poll_search_source(source, fetcher, db, notifier, rules) -> int:
    return poll_search_source_with_stats(source, fetcher, db, notifier, rules).notifications_sent



def audit_search_source_ids(source, fetcher, db, watched_ids: set[str] | None = None) -> SearchAuditStats:
    stats = SearchAuditStats(
        source_name=source.name,
        source_url=source.url,
        missing_ids=[],
        missing_results=[],
        watched_missing_ids=[],
    )
    site_ids: set[str] = set()
    search_results_by_id: dict[str, dict[str, object]] = {}
    watched = watched_ids or set()

    try:
        for _page_url, search_html, page_results in _iterate_search_pages(source.url, fetcher):
            stats.pages_fetched += 1
            if stats.site_total is None:
                stats.site_total = parse_search_total_items(search_html)
            for result in page_results:
                site_id = str(result.get("site_id", "")).strip()
                if site_id:
                    site_ids.add(site_id)
                    search_results_by_id.setdefault(site_id, result)
    except Exception as exc:
        stats.errors = 1
        stats.error_message = str(exc)
        return stats

    known_ids = db.list_listing_site_ids()
    missing = sorted(site_ids - known_ids)
    stats.parsed_unique_ids = len(site_ids)
    stats.in_db = len(site_ids & known_ids)
    stats.missing_ids = missing
    stats.missing_results = [search_results_by_id[site_id] for site_id in missing if site_id in search_results_by_id]
    stats.watched_missing_ids = [site_id for site_id in missing if site_id in watched]
    return stats


def recover_audit_missing_results(
    source,
    audit: SearchAuditStats,
    fetcher,
    db,
    notifier,
    rules,
    *,
    max_failures: int = 3,
) -> PollSourceStats:
    stats = PollSourceStats(source_name=f"{source.name}:audit-recovery", source_url=source.url)
    missing_results = audit.missing_results or []

    for result in missing_results:
        site_id = str(result.get("site_id", "")).strip()
        detail_url = str(result.get("url", "")).strip()
        if not site_id or not detail_url:
            continue
        if db.get_listing_by_site_id(site_id) is not None:
            db.clear_audit_recovery_failure(site_id)
            continue

        stats.search_results += 1
        try:
            detail_html = fetcher.fetch_text(detail_url)
            stats.details_fetched += 1
            detail = parse_listing_detail(detail_html, detail_url)
            listing = _build_listing(result, detail)
            existing, _snapshot, _features, evaluation, snapshot_inserted = _persist_listing_analysis(
                db,
                listing,
                result,
                detail,
                rules,
                source.location_blacklist,
            )
            if snapshot_inserted:
                stats.snapshots_inserted += 1
            else:
                stats.snapshots_skipped += 1
            db.clear_audit_recovery_failure(site_id)

            event = process_listing_event(
                existing_price=existing.price_current if existing else None,
                new_price=listing.price_current,
                passes_realtime=evaluation.passes_realtime,
            )
            if event == "new_listing":
                stats.new_listings += 1
                summary = db.get_listing_summary_by_site_id(listing.site_id)
                notifier.send_message(render_listing_card(summary, is_saved=False, badge="НОВОЕ"), parse_mode="HTML")
                stats.notifications_sent += 1
        except Exception as exc:
            stats.errors += 1
            stats.error_message = str(exc)
            failure = db.record_audit_recovery_failure(
                site_id=site_id,
                source_name=source.name,
                detail_url=detail_url,
                error_message=str(exc),
            )
            attempts = int(failure["attempts"])
            if attempts >= max_failures and not failure.get("alert_sent_at"):
                notifier.send_message(
                    "\n".join(
                        [
                            "AUDIT RECOVERY FAILED",
                            f"source: {source.name}",
                            f"site_id: {site_id}",
                            f"attempts: {attempts}",
                            f"url: {detail_url}",
                            f"error: {exc}",
                        ]
                    )
                )
                db.mark_audit_recovery_alert_sent(site_id)

    return stats



def poll_search_source_with_stats(source, fetcher, db, notifier, rules) -> PollSourceStats:
    stats = PollSourceStats(source_name=source.name, source_url=source.url)
    seen_site_ids: set[str] = set()

    for _page_url, _search_html, page_results in _iterate_search_pages(source.url, fetcher):
        stats.pages_fetched += 1
        for result in page_results:
            site_id = str(result.get("site_id", "")).strip()
            if not site_id or site_id in seen_site_ids:
                continue
            seen_site_ids.add(site_id)
            stats.search_results += 1

            detail_url = str(result["url"])
            detail_html = fetcher.fetch_text(detail_url)
            stats.details_fetched += 1
            detail = parse_listing_detail(detail_html, detail_url)
            listing = _build_listing(result, detail)
            existing, _snapshot, _features, evaluation, snapshot_inserted = _persist_listing_analysis(
                db,
                listing,
                result,
                detail,
                rules,
                source.location_blacklist,
            )
            if snapshot_inserted:
                stats.snapshots_inserted += 1
            else:
                stats.snapshots_skipped += 1

            event = process_listing_event(
                existing_price=existing.price_current if existing else None,
                new_price=listing.price_current,
                passes_realtime=evaluation.passes_realtime,
            )
            if existing and listing.price_current != existing.price_current:
                price_event = db.record_price(existing.id or 0, listing.price_current)
                if price_event == "price_drop":
                    stats.price_drops += 1
                elif price_event == "price_rise":
                    stats.price_rises += 1
                if price_event in {"price_drop", "price_rise"}:
                    current_status = db.get_listing_status(existing.id or 0)
                    if current_status and current_status["status"] == "rejected":
                        db.set_listing_status(existing.id or 0, "new")
            if event == "new_listing":
                stats.new_listings += 1
                summary = db.get_listing_summary_by_site_id(listing.site_id)
                notifier.send_message(render_listing_card(summary, is_saved=False, badge="НОВОЕ"), parse_mode="HTML")
                stats.notifications_sent += 1
            elif event in {"price_drop", "price_rise"} and existing is not None:
                summary = db.get_listing_summary_by_site_id(listing.site_id)
                notifier.send_message(render_listing_card(summary, is_saved=False, badge="ЦЕНА ИЗМЕНИЛАСЬ"), parse_mode="HTML")
                stats.notifications_sent += 1

    return stats



def import_exported_manifest(manifest_path: Path, db, rules) -> int:
    path = Path(manifest_path)
    items = json.loads(path.read_text(encoding="utf-8"))
    imported = 0
    for item in items:
        html_path = Path(str(item["html_path"]))
        if not html_path.is_absolute():
            candidates = [
                html_path,
                path.parent / html_path,
                Path.cwd() / html_path,
            ]
            resolved = next((candidate.resolve() for candidate in candidates if candidate.exists()), None)
            if resolved is None:
                resolved = (path.parent / html_path).resolve()
            html_path = resolved
        detail_html = html_path.read_text(encoding="utf-8")
        detail_url = str(item["url"])
        detail = parse_listing_detail(detail_html, detail_url)
        listing = _build_listing(item, detail)
        _persist_listing_analysis(db, listing, item, detail, rules, [])
        imported += 1
    return imported
