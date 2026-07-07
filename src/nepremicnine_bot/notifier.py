import httpx



def format_realtime_message(listing: dict[str, object], evaluation: dict[str, object]) -> str:
    return "\n".join(
        [
            f"{listing['title']}",
            f"Price: {listing['price_current']}",
            f"Area: {listing['area']}",
            f"Location: {listing['location_text']}",
            f"Utilities: {evaluation['utilities_status']}",
            str(listing['url']),
        ]
    )



def format_price_drop_message(listing: dict[str, object], old_price: int) -> str:
    return "\n".join(
        [
            f"{listing['title']}",
            f"Price dropped: {old_price} -> {listing['price_current']}",
            f"Location: {listing['location_text']}",
            str(listing['url']),
        ]
    )


class TelegramNotifier:
    def __init__(self, bot_token: str, chat_id: str):
        self.bot_token = bot_token
        self.chat_id = chat_id

    def send_message(self, text: str, parse_mode: str | None = None) -> None:
        payload = {"chat_id": self.chat_id, "text": text, "disable_web_page_preview": True}
        if parse_mode is not None:
            payload["parse_mode"] = parse_mode
        httpx.post(
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
            json=payload,
            timeout=10.0,
        ).raise_for_status()
