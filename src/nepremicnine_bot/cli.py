import argparse
import sys
from pathlib import Path

from nepremicnine_bot.bot import TelegramBotClient, run_command_bot
from nepremicnine_bot.config import Settings
from nepremicnine_bot.fetcher import build_fetcher
from nepremicnine_bot.notifier import TelegramNotifier
from nepremicnine_bot.runner import (
    PollSourceStats,
    SearchAuditStats,
    audit_search_source_ids,
    import_exported_manifest,
    poll_search_source,
    poll_search_source_with_stats,
    recover_audit_missing_results,
)
from nepremicnine_bot.storage import Database


DEFAULT_WARM_URL = "https://www.nepremicnine.net/nepremicnine.html"
DEFAULT_STORAGE_STATE_PATH = "./data/storage-state.json"



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    poll = subparsers.add_parser("poll")
    poll.add_argument("--window", choices=["full", "daily"], default="full")
    poll.add_argument("--audit-recover", action="store_true")
    audit = subparsers.add_parser("audit")
    audit.add_argument("--window", choices=["full", "daily"], default="full")
    subparsers.add_parser("digest")
    subparsers.add_parser("bot")
    warm = subparsers.add_parser("warm-browser")
    warm.add_argument("url", nargs="?", default=DEFAULT_WARM_URL)
    check = subparsers.add_parser("check-session")
    check.add_argument("url", nargs="?", default=DEFAULT_WARM_URL)
    export = subparsers.add_parser("export-session")
    export.add_argument("url", nargs="?", default=DEFAULT_WARM_URL)
    import_exported = subparsers.add_parser("import-exported")
    import_exported.add_argument("manifest_path")
    return parser



def _source_for_window(source, window: str):
    if window == "daily":
        return source.model_copy(update={"url": source.daily_url or source.url})
    return source.model_copy(update={"url": source.full_url or source.url})


def run_poll(settings: Settings, fetcher, db: Database, notifier: TelegramNotifier, *, window: str = "full") -> int:
    return sum(stat.notifications_sent for stat in run_poll_with_stats(settings, fetcher, db, notifier, window=window))


def run_poll_with_stats(
    settings: Settings,
    fetcher,
    db: Database,
    notifier: TelegramNotifier,
    *,
    window: str = "full",
    audit_recover: bool = False,
) -> list[PollSourceStats]:
    db.initialize()
    watched_ids = {str(item).strip() for item in getattr(settings, "audit_watch_ids", []) if str(item).strip()}
    stats: list[PollSourceStats] = []
    for source in settings.load_search_sources():
        if not source.enabled:
            continue
        active_source = _source_for_window(source, window)
        try:
            stats.append(poll_search_source_with_stats(active_source, fetcher, db, notifier, settings.rules))
        except Exception as exc:
            stats.append(
                PollSourceStats(
                    source_name=active_source.name,
                    source_url=active_source.url,
                    errors=1,
                    error_message=str(exc),
                )
            )
            continue
        if audit_recover:
            audit = audit_search_source_ids(active_source, fetcher, db, watched_ids)
            stats.append(recover_audit_missing_results(active_source, audit, fetcher, db, notifier, settings.rules))
    return stats


def run_search_audit_with_stats(
    settings: Settings,
    fetcher,
    db: Database,
    *,
    window: str = "full",
) -> list[SearchAuditStats]:
    db.initialize()
    watched_ids = {str(item).strip() for item in getattr(settings, "audit_watch_ids", []) if str(item).strip()}
    stats: list[SearchAuditStats] = []
    for source in settings.load_search_sources():
        if not source.enabled:
            continue
        stats.append(audit_search_source_ids(_source_for_window(source, window), fetcher, db, watched_ids))
    return stats



def _storage_state_path(settings: Settings) -> str:
    return getattr(settings, "browser_storage_state_path", DEFAULT_STORAGE_STATE_PATH)



def _build_browser_fetcher(settings: Settings):
    return build_fetcher(
        "browser",
        browser_user_data_dir=settings.browser_user_data_dir,
        browser_headless=settings.browser_headless,
        browser_channel=settings.browser_channel,
        browser_proxy=settings.browser_proxy,
        browser_cookies_path=settings.browser_cookies_path,
        browser_storage_state_path=_storage_state_path(settings),
    )



def _safe_console_text(value: object, encoding: str | None = None) -> str:
    target_encoding = encoding or getattr(sys.stdout, "encoding", None) or "utf-8"
    return str(value).encode(target_encoding, errors="backslashreplace").decode(target_encoding, errors="replace")



def _print_session_result(result: dict[str, object], prefix: str) -> None:
    status = f"{prefix} OK" if result.get("ok") else f"{prefix} BLOCKED"
    print(f"{status}: {_safe_console_text(result.get('title', ''))}")
    print(f"URL: {_safe_console_text(result.get('url', DEFAULT_WARM_URL))}")
    print(f"Cookies loaded: {result.get('cookies_loaded', 0)}")
    print(f"Origins loaded: {result.get('origins_loaded', 0)}")
    print(f"Cookies saved: {result.get('cookies_saved', 0)}")
    print(f"Storage cookies saved: {result.get('storage_cookies_saved', 0)}")



def _print_poll_stats(stats: list[PollSourceStats]) -> None:
    total = PollSourceStats(source_name="total", source_url="")
    for item in stats:
        total.pages_fetched += item.pages_fetched
        total.search_results += item.search_results
        total.details_fetched += item.details_fetched
        total.new_listings += item.new_listings
        total.price_drops += item.price_drops
        total.price_rises += item.price_rises
        total.snapshots_inserted += item.snapshots_inserted
        total.snapshots_skipped += item.snapshots_skipped
        total.notifications_sent += item.notifications_sent
        total.errors += item.errors
        print(
            "Source "
            f"{_safe_console_text(item.source_name)}: "
            f"pages={item.pages_fetched} "
            f"results={item.search_results} "
            f"details={item.details_fetched} "
            f"new={item.new_listings} "
            f"drops={item.price_drops} "
            f"rises={item.price_rises} "
            f"snapshots_inserted={item.snapshots_inserted} "
            f"snapshots_skipped={item.snapshots_skipped} "
            f"notifications={item.notifications_sent} "
            f"errors={item.errors}"
        )
        if item.error_message:
            print(f"  error: {_safe_console_text(item.error_message)}")
    print(
        "Total: "
        f"pages={total.pages_fetched} "
        f"results={total.search_results} "
        f"details={total.details_fetched} "
        f"new={total.new_listings} "
        f"drops={total.price_drops} "
        f"rises={total.price_rises} "
        f"snapshots_inserted={total.snapshots_inserted} "
        f"snapshots_skipped={total.snapshots_skipped} "
        f"notifications={total.notifications_sent} "
        f"errors={total.errors}"
    )


def _print_search_audit_stats(stats: list[SearchAuditStats]) -> None:
    total_site = 0
    total_parsed = 0
    total_in_db = 0
    total_missing = 0
    total_errors = 0
    watched_missing: set[str] = set()
    for item in stats:
        missing_ids = item.missing_ids or []
        watched_ids = item.watched_missing_ids or []
        total_site += item.site_total or 0
        total_parsed += item.parsed_unique_ids
        total_in_db += item.in_db
        total_missing += len(missing_ids)
        total_errors += item.errors
        watched_missing.update(watched_ids)
        print(
            "Audit "
            f"{_safe_console_text(item.source_name)}: "
            f"pages={item.pages_fetched} "
            f"site_total={item.site_total if item.site_total is not None else 'unknown'} "
            f"parsed_unique={item.parsed_unique_ids} "
            f"in_db={item.in_db} "
            f"missing={len(missing_ids)} "
            f"watched_missing={len(watched_ids)} "
            f"errors={item.errors}"
        )
        if missing_ids:
            print(f"  missing_ids={_safe_console_text(','.join(missing_ids))}")
        if watched_ids:
            print(f"  watched_missing_ids={_safe_console_text(','.join(watched_ids))}")
        if item.error_message:
            print(f"  error: {_safe_console_text(item.error_message)}")
    print(
        "Audit Total: "
        f"site_total={total_site} "
        f"parsed_unique={total_parsed} "
        f"in_db={total_in_db} "
        f"missing={total_missing} "
        f"watched_missing={len(watched_missing)} "
        f"errors={total_errors}"
    )



def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "poll":
        settings = Settings()
        bot_token = getattr(settings, "bot_token", None) or getattr(settings, "telegram_bot_token", None)
        chat_id = getattr(settings, "chat_id", None) or getattr(settings, "telegram_chat_id", None)
        if not bot_token or not chat_id:
            raise ValueError("NEPREMICNINE_BOT_TOKEN and NEPREMICNINE_CHAT_ID are required for poll")
        fetcher = build_fetcher(
            settings.fetch_mode,
            browser_user_data_dir=settings.browser_user_data_dir,
            browser_headless=settings.browser_headless,
            browser_channel=settings.browser_channel,
            browser_proxy=settings.browser_proxy,
            browser_cookies_path=settings.browser_cookies_path,
            browser_storage_state_path=_storage_state_path(settings),
        )
        db = Database(Path(settings.db_path))
        notifier = TelegramNotifier(bot_token, chat_id)
        stats = run_poll_with_stats(settings, fetcher, db, notifier, window=args.window, audit_recover=args.audit_recover)
        _print_poll_stats(stats)
        sent = sum(item.notifications_sent for item in stats)
        print(f"Sent {sent} notifications")
        if any(item.errors for item in stats):
            raise SystemExit(1)
    elif args.command == "audit":
        settings = Settings()
        fetcher = build_fetcher(
            settings.fetch_mode,
            browser_user_data_dir=settings.browser_user_data_dir,
            browser_headless=settings.browser_headless,
            browser_channel=settings.browser_channel,
            browser_proxy=settings.browser_proxy,
            browser_cookies_path=settings.browser_cookies_path,
            browser_storage_state_path=_storage_state_path(settings),
        )
        db = Database(Path(settings.db_path))
        stats = run_search_audit_with_stats(settings, fetcher, db, window=args.window)
        _print_search_audit_stats(stats)
        if any(item.errors for item in stats):
            raise SystemExit(1)
    elif args.command == "warm-browser":
        settings = Settings()
        fetcher = _build_browser_fetcher(settings)
        result = fetcher.warm_session(args.url) or {}
        print("Browser session warmed")
        print(f"Cookies saved: {result.get('cookies_saved', 0)}")
        print(f"Storage cookies saved: {result.get('storage_cookies_saved', 0)}")
    elif args.command == "check-session":
        settings = Settings()
        fetcher = _build_browser_fetcher(settings)
        result = fetcher.check_session(args.url)
        _print_session_result(result, "Session")
    elif args.command == "export-session":
        settings = Settings()
        fetcher = _build_browser_fetcher(settings)
        result = fetcher.export_session(args.url)
        _print_session_result(result, "Export")
    elif args.command == "import-exported":
        settings = Settings()
        db = Database(Path(settings.db_path))
        db.initialize()
        imported = import_exported_manifest(Path(args.manifest_path), db, settings.rules)
        print(f"Imported {imported} listings")
    elif args.command == "digest":
        print("digest")
    elif args.command == "bot":
        settings = Settings()
        db = Database(Path(settings.db_path))
        db.initialize()
        client = TelegramBotClient(settings.telegram_bot_token)
        print("Bot polling started")
        run_command_bot(client, settings.telegram_chat_id, db)
    else:
        raise ValueError(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
