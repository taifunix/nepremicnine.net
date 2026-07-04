import argparse
from pathlib import Path

from nepremicnine_bot.config import Settings
from nepremicnine_bot.fetcher import build_fetcher
from nepremicnine_bot.notifier import TelegramNotifier
from nepremicnine_bot.runner import poll_search_source
from nepremicnine_bot.storage import Database



def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("poll")
    subparsers.add_parser("digest")
    subparsers.add_parser("bot")
    return parser



def run_poll(settings: Settings, fetcher, db: Database, notifier: TelegramNotifier) -> int:
    db.initialize()
    total_sent = 0
    for source in settings.load_search_sources():
        if not source.enabled:
            continue
        total_sent += poll_search_source(source, fetcher, db, notifier, settings.rules)
    return total_sent



def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "poll":
        settings = Settings()
        fetcher = build_fetcher(settings.fetch_mode)
        db = Database(Path(settings.db_path))
        notifier = TelegramNotifier(settings.telegram_bot_token, settings.telegram_chat_id)
        sent = run_poll(settings, fetcher, db, notifier)
        print(f"Sent {sent} notifications")
    elif args.command == "digest":
        print("digest")
    else:
        print("bot")
