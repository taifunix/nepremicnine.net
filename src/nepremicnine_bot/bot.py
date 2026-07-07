from __future__ import annotations

import html
import re
import time
from datetime import datetime, timedelta

import httpx


ISO_PREFIX_LENGTH = 16
DEFAULT_LIST_LIMIT = 5
MAX_LIST_LIMIT = 50
CARD_TTL_MINUTES = 90
TELEGRAM_RETRY_SLEEP_SECONDS = 15
TELEGRAM_CARD_BATCH_SIZE = 3
TELEGRAM_CARD_BATCH_PAUSE_SECONDS = 8
ROOM_COUNT_TITLE_PATTERN = re.compile(r'\b(\d+(?:[.,]\d+)?)-sobno\b', re.IGNORECASE)
LAND_AREA_ATTRIBUTE_PATTERN = re.compile(r'zemlji[^\s:]*\s*:\s*(\d+(?:[.,]\d+)?)\s*m\s*2', re.IGNORECASE)
LAND_AREA_INLINE_PATTERN = re.compile(r'(\d+(?:[.,]\d+)?)\s*m\s*2\s*zemlji\S*', re.IGNORECASE)
ATRIUM_PATTERN = re.compile(r'\batrij(?:\b|a\b|u\b|em\b|i\b)', re.IGNORECASE)
GARDEN_PATTERN = re.compile(r'\bvrt(?:\b|a\b|e\b|u\b|om\b|na\b|ni\b|no\b)', re.IGNORECASE)
SELLER_TYPE_ORDER = ("all", "private", "agency")
SELLER_TYPE_LABELS = {
    "all": "все",
    "private": "собственник",
    "agency": "агентство",
}



class TelegramBotClient:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token

    def get_updates(self, *, offset: int | None = None, timeout: int = 30):
        payload = {"timeout": timeout}
        if offset is not None:
            payload["offset"] = offset
        response = httpx.post(
            f"https://api.telegram.org/bot{self.bot_token}/getUpdates",
            json=payload,
            timeout=timeout + 5,
        )
        response.raise_for_status()
        data = response.json()
        return data.get("result", [])

    def send_message(self, chat_id: str, text: str, reply_markup=None, parse_mode: str | None = None) -> int | None:
        payload = {
            "chat_id": chat_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if parse_mode is not None:
            payload["parse_mode"] = parse_mode
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        response = httpx.post(
            f"https://api.telegram.org/bot{self.bot_token}/sendMessage",
            json=payload,
            timeout=10.0,
        )
        response.raise_for_status()
        data = response.json()
        result = data.get("result") or {}
        message_id = result.get("message_id")
        return int(message_id) if message_id is not None else None

    def edit_message_text(self, chat_id: str, message_id: int, text: str, reply_markup=None, parse_mode: str | None = None) -> None:
        payload = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "disable_web_page_preview": True,
        }
        if parse_mode is not None:
            payload["parse_mode"] = parse_mode
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        httpx.post(
            f"https://api.telegram.org/bot{self.bot_token}/editMessageText",
            json=payload,
            timeout=10.0,
        ).raise_for_status()

    def delete_message(self, chat_id: str, message_id: int) -> None:
        httpx.post(
            f"https://api.telegram.org/bot{self.bot_token}/deleteMessage",
            json={"chat_id": chat_id, "message_id": message_id},
            timeout=10.0,
        ).raise_for_status()

    def answer_callback_query(self, callback_query_id: str, text: str | None = None) -> None:
        payload = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
        httpx.post(
            f"https://api.telegram.org/bot{self.bot_token}/answerCallbackQuery",
            json=payload,
            timeout=10.0,
        ).raise_for_status()



def _now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat()



def _delete_after_iso(now_iso: str) -> str:
    return (datetime.fromisoformat(now_iso) + timedelta(minutes=CARD_TTL_MINUTES)).replace(microsecond=0).isoformat()



def _looks_like_schedule_token(token: str) -> bool:
    return len(token) >= ISO_PREFIX_LENGTH and token[4] == "-" and "T" in token



def _parse_limit(command: str) -> int:
    parts = command.split(maxsplit=1)
    if len(parts) == 1:
        return DEFAULT_LIST_LIMIT
    try:
        value = int(parts[1])
    except ValueError as exc:
        raise ValueError("Command limit must be an integer") from exc
    return max(1, min(value, MAX_LIST_LIMIT))



def _normalize_room_count_for_ru(room_count_text: str) -> str:
    value = room_count_text.strip()
    if value.lower().endswith("-sobno"):
        value = value[:-6]
    return value.strip()


def _fallback_room_count_text(summary: dict[str, object]) -> str:
    room_count_text = str(summary.get("room_count_text", "")).strip()
    if room_count_text:
        return room_count_text
    for source in (str(summary.get("title", "")), str(summary.get("url", ""))):
        match = ROOM_COUNT_TITLE_PATTERN.search(source)
        if match:
            return match.group(0)
    return ""


def _display_date_text(summary: dict[str, object]) -> str:
    display_date_text = str(summary.get("display_date_text", "")).strip()
    if display_date_text:
        return display_date_text
    published_at_text = str(summary.get("published_at_text", "")).strip()
    if published_at_text:
        return published_at_text
    captured_at = str(summary.get("captured_at", "")).strip()
    if len(captured_at) >= 10:
        return captured_at[:10]
    return ""



def _format_price_eur(price_current: int | object) -> str:
    try:
        return f"{int(price_current)}€"
    except (TypeError, ValueError):
        return ""


def _bold_value(value: object) -> str:
    return f"<b>{html.escape(str(value))}</b>"


def _build_price_line(summary: dict[str, object]) -> str:
    current = _format_price_eur(summary.get("price_current"))
    if not current:
        return ""
    previous_raw = summary.get("previous_price")
    if previous_raw is None:
        return f"Цена: {_bold_value(current)}"
    previous = _format_price_eur(previous_raw)
    if not previous or previous == current:
        return f"Цена: {_bold_value(current)}"
    return f"Цена: {_bold_value(current)} (было {_bold_value(previous)})"



def _format_area_ru(area: float | object) -> str:
    try:
        value = float(area)
    except (TypeError, ValueError):
        return ""
    text = f"{value:g}".replace(".", ",")
    return f"{text} м²"



def _build_bedroom_line(summary: dict[str, object]) -> str:
    match = str(summary.get("two_bedroom_match", "")).strip().lower()
    bedroom_count_guess = summary.get("bedroom_count_guess")
    if match == "maybe":
        return f"Спальни: {_bold_value('спорно')}"
    if bedroom_count_guess is not None:
        return f"Спальни: {_bold_value(bedroom_count_guess)}"
    if match == "yes":
        return f"Спальни: {_bold_value(2)}"
    return ""



def _build_utilities_line(summary: dict[str, object]) -> str:
    status = str(summary.get("utilities_status", "")).strip().lower()
    mapping = {
        "included_yes": "включены",
        "partial": "частично включены",
        "included_partial": "частично включены",
        "no": "отдельно",
    }
    value = mapping.get(status, "")
    return f"Коммунальные: {_bold_value(value)}" if value else ""


def _normalize_land_text(value: str) -> str:
    normalized = value.lower()
    normalized = normalized.translate(
        str.maketrans(
            {
                "š": "s",
                "č": "c",
                "ž": "z",
                "ć": "c",
            }
        )
    )
    return " ".join(normalized.split())


def _format_land_area(value: float) -> str:
    if value.is_integer():
        return str(int(value))
    return f"{value:g}".replace(".", ",")


def _extract_land_area(summary: dict[str, object]) -> float | None:
    for field in ("detail_attributes_text", "detail_top_tab_text", "detail_item_description", "detail_description"):
        normalized = _normalize_land_text(str(summary.get(field, "")))
        if not normalized:
            continue
        match = LAND_AREA_ATTRIBUTE_PATTERN.search(normalized) or LAND_AREA_INLINE_PATTERN.search(normalized)
        if not match:
            continue
        raw_value = next(group for group in match.groups() if group is not None)
        area = float(raw_value.replace(",", "."))
        if area > 0:
            return area
    return None


def _build_land_garden_line(summary: dict[str, object]) -> str:
    sources = [
        _normalize_land_text(str(summary.get("detail_attributes_text", ""))),
        _normalize_land_text(str(summary.get("detail_top_tab_text", ""))),
        _normalize_land_text(str(summary.get("detail_item_description", ""))),
        _normalize_land_text(str(summary.get("detail_description", ""))),
    ]
    combined = " ".join(source for source in sources if source)
    if not combined:
        return ""

    parts: list[str] = []
    land_area = _extract_land_area(summary)
    has_atrium = bool(ATRIUM_PATTERN.search(combined))
    has_garden = bool(GARDEN_PATTERN.search(combined))

    if land_area is not None:
        parts.append(f"земля {_format_land_area(land_area)}")
    elif has_atrium:
        parts.append("земля")

    if has_garden:
        parts.append("сад")

    if not parts:
        return ""
    return f"Земля/сад: {_bold_value(', '.join(parts))}"



def _format_note_lines(notes: list[dict[str, str | None]]) -> list[str]:
    if not notes:
        return []
    lines = ["", "Заметки:"]
    for note in notes:
        note_text = str(note.get("note_text", "")).strip()
        if not note_text:
            continue
        lines.append(f"• {html.escape(note_text)}")
    return lines



def _render_listing_with_notes(summary: dict[str, object], db=None, *, is_saved: bool) -> str:
    card = render_listing_card(summary, is_saved=is_saved)
    if db is not None and is_saved:
        listing_id = int(summary.get("listing_id", 0) or 0)
        notes = db.list_listing_notes(listing_id) if listing_id else []
        note_lines = _format_note_lines(notes)
        if note_lines:
            card = "\n".join([card, *note_lines])
    return card



def _compact_listing_preview(summary: dict[str, object], db=None) -> str:
    site_id = str(summary.get("site_id", "")).strip()
    is_saved = str(summary.get("status", "")) == "saved"
    card = _render_listing_with_notes(summary, db=db, is_saved=is_saved)
    if site_id:
        return f"{site_id}\n{card}"
    return card



def parse_note_command(command: str) -> dict[str, str | None]:
    _, site_id, status, *rest = command.split()
    if not rest:
        raise ValueError("/note command requires note text")

    scheduled_for = None
    note_parts = rest
    if rest and _looks_like_schedule_token(rest[0]):
        scheduled_for = rest[0]
        note_parts = rest[1:]

    if not note_parts:
        raise ValueError("/note command requires note text")

    return {
        "site_id": site_id,
        "status": status,
        "scheduled_for": scheduled_for,
        "note_text": " ".join(note_parts),
    }



def parse_status_command(command: str) -> dict[str, str]:
    _, site_id, status = command.split(maxsplit=2)
    return {"site_id": site_id, "status": status}



def _get_listing_or_raise(db, site_id: str):
    listing = db.get_listing_by_site_id(site_id)
    if listing is None or listing.id is None:
        raise ValueError(f"Unknown listing site_id: {site_id}")
    return listing



def build_help_message() -> str:
    return "\n".join(
        [
            "Доступно:",
            "Новые",
            "Избранное",
            "Дорогие",
            "Настройки",
            "/latest [N]",
            "/saved [N]",
            "/expensive [N]",
            "/show <site_id>",
            "/status <site_id> <status>",
            "/note <site_id> <status> [YYYY-MM-DDTHH:MM] <text>",
            "/help",
        ]
    )



def build_main_menu_keyboard() -> dict[str, object]:
    return {
        "keyboard": [[{"text": "Новые"}, {"text": "Избранное"}, {"text": "Дорогие"}], [{"text": "Настройки"}]],
        "resize_keyboard": True,
        "is_persistent": True,
    }



def build_card_keyboard(site_id: str) -> dict[str, object]:
    return {
        "inline_keyboard": [
            [
                {"text": "Сохранить", "callback_data": f"save:{site_id}"},
                {"text": "Дорого", "callback_data": f"expensive:{site_id}"},
                {"text": "Не подходит", "callback_data": f"reject:{site_id}"},
            ]
        ]
    }


def _format_settings_range(min_value, max_value) -> str:
    if min_value is None and max_value is None:
        return "не задано"
    left = str(int(min_value)) if isinstance(min_value, float) and min_value.is_integer() else (str(min_value) if min_value is not None else "-")
    right = str(int(max_value)) if isinstance(max_value, float) and max_value.is_integer() else (str(max_value) if max_value is not None else "-")
    return f"{left}-{right}"


def build_settings_keyboard(settings: dict[str, object]) -> dict[str, object]:
    disputed_label = "Спорно: да" if settings.get("include_maybe", True) else "Спорно: нет"
    seller_label = f"Кто сдает: {SELLER_TYPE_LABELS.get(str(settings.get('seller_type', 'all')), 'все')}"
    return {
        "inline_keyboard": [
            [{"text": "Цена", "callback_data": "settings:price"}, {"text": "Площадь", "callback_data": "settings:area"}],
            [{"text": "Спальни", "callback_data": "settings:bedrooms"}, {"text": disputed_label, "callback_data": "settings:maybe:toggle"}],
            [{"text": seller_label, "callback_data": "settings:seller:cycle"}],
            [{"text": "Сбросить", "callback_data": "settings:reset"}],
        ]
    }


def handle_settings_command(chat_id: str, db) -> tuple[str, dict[str, object]]:
    settings = db.get_chat_settings(chat_id)
    text = "\n".join(
        [
            "Настройки фильтра:",
            f"Цена: {_format_settings_range(settings['price_min'], settings['price_max'])}",
            f"Площадь: {_format_settings_range(settings['area_min'], settings['area_max'])}",
            f"Спальни: {_format_settings_range(settings['bedrooms_min'], settings['bedrooms_max'])}",
            f"Показывать спорные: {'да' if settings.get('include_maybe', True) else 'нет'}",
            f"Кто сдает: {SELLER_TYPE_LABELS.get(str(settings.get('seller_type', 'all')), 'все')}",
        ]
    )
    return text, build_settings_keyboard(settings)


def _normalize_bedroom_count(summary: dict[str, object]) -> int | None:
    guess = summary.get("bedroom_count_guess")
    if guess is not None:
        return int(guess)
    match = str(summary.get("two_bedroom_match", "")).strip().lower()
    if match in {"yes", "maybe"}:
        return 2
    return None


def _matches_chat_filters(summary: dict[str, object], settings: dict[str, object]) -> bool:
    price_current = int(summary.get("price_current", 0) or 0)
    area = float(summary.get("area", 0) or 0)
    bedrooms = _normalize_bedroom_count(summary)
    match = str(summary.get("two_bedroom_match", "")).strip().lower()
    seller_type = str(settings.get("seller_type", "all") or "all")

    if not settings.get("include_maybe", True) and match == "maybe":
        return False
    if seller_type == "private" and not summary.get("is_private"):
        return False
    if seller_type == "agency" and not summary.get("is_agency"):
        return False
    if settings.get("price_min") is not None and price_current < int(settings["price_min"]):
        return False
    if settings.get("price_max") is not None and price_current > int(settings["price_max"]):
        return False
    if settings.get("area_min") is not None and area < float(settings["area_min"]):
        return False
    if settings.get("area_max") is not None and area > float(settings["area_max"]):
        return False
    if settings.get("bedrooms_min") is not None:
        if bedrooms is None or bedrooms < int(settings["bedrooms_min"]):
            return False
    if settings.get("bedrooms_max") is not None:
        if bedrooms is None or bedrooms > int(settings["bedrooms_max"]):
            return False
    return True


def _parse_range_input(text: str, *, allow_float: bool) -> tuple[int | float | None, int | float | None]:
    parts = text.split()
    if len(parts) != 2:
        raise ValueError("Нужно ввести два значения: min max")

    def _convert(raw: str):
        token = raw.strip()
        if token in {"-", "_", "*"}:
            return None
        if allow_float:
            return float(token.replace(",", "."))
        return int(token)

    return _convert(parts[0]), _convert(parts[1])


def _handle_pending_settings_input(chat_id: str, text: str, client, db) -> bool:
    state = db.get_chat_input_state(chat_id)
    if not state:
        return False
    try:
        if state == "price":
            left, right = _parse_range_input(text, allow_float=False)
            db.upsert_chat_settings(chat_id, {"price_min": left, "price_max": right})
        elif state == "area":
            left, right = _parse_range_input(text, allow_float=True)
            db.upsert_chat_settings(chat_id, {"area_min": left, "area_max": right})
        elif state == "bedrooms":
            left, right = _parse_range_input(text, allow_float=False)
            db.upsert_chat_settings(chat_id, {"bedrooms_min": left, "bedrooms_max": right})
        else:
            return False
    except ValueError as exc:
        client.send_message(chat_id, f"Ошибка: {exc}")
        return True

    db.clear_chat_input_state(chat_id)
    settings_text, settings_keyboard = handle_settings_command(chat_id, db)
    client.send_message(chat_id, settings_text, reply_markup=settings_keyboard)
    return True


def _cycle_seller_type(current: object) -> str:
    current_value = str(current or "all")
    try:
        index = SELLER_TYPE_ORDER.index(current_value)
    except ValueError:
        return "all"
    return SELLER_TYPE_ORDER[(index + 1) % len(SELLER_TYPE_ORDER)]


def _handle_settings_callback(callback_query: dict[str, object], client, db) -> bool:
    data = str(callback_query.get("data", "")).strip()
    if not data.startswith("settings:"):
        return False
    callback_query_id = str(callback_query.get("id", "")).strip()
    message = callback_query.get("message") or {}
    chat_id = str((message.get("chat") or {}).get("id", ""))
    message_id = int(message.get("message_id", 0) or 0)

    if data == "settings:price":
        db.set_chat_input_state(chat_id, "price")
        client.send_message(chat_id, "Введите диапазон цены: min max. Для пустого значения используйте -")
    elif data == "settings:area":
        db.set_chat_input_state(chat_id, "area")
        client.send_message(chat_id, "Введите диапазон площади: min max. Для пустого значения используйте -")
    elif data == "settings:bedrooms":
        db.set_chat_input_state(chat_id, "bedrooms")
        client.send_message(chat_id, "Введите диапазон спален: min max. Для пустого значения используйте -")
    elif data == "settings:maybe:toggle":
        settings = db.get_chat_settings(chat_id)
        db.upsert_chat_settings(chat_id, {"include_maybe": not settings.get("include_maybe", True)})
        settings_text, settings_keyboard = handle_settings_command(chat_id, db)
        client.edit_message_text(chat_id, message_id, settings_text, reply_markup=settings_keyboard)
    elif data == "settings:seller:cycle":
        settings = db.get_chat_settings(chat_id)
        db.upsert_chat_settings(chat_id, {"seller_type": _cycle_seller_type(settings.get("seller_type", "all"))})
        settings_text, settings_keyboard = handle_settings_command(chat_id, db)
        client.edit_message_text(chat_id, message_id, settings_text, reply_markup=settings_keyboard)
    elif data == "settings:reset":
        db.upsert_chat_settings(
            chat_id,
            {
                "price_min": None,
                "price_max": None,
                "area_min": None,
                "area_max": None,
                "bedrooms_min": None,
                "bedrooms_max": None,
                "include_maybe": True,
                "seller_type": "all",
            },
        )
        db.clear_chat_input_state(chat_id)
        settings_text, settings_keyboard = handle_settings_command(chat_id, db)
        client.edit_message_text(chat_id, message_id, settings_text, reply_markup=settings_keyboard)
    else:
        return False

    if callback_query_id and hasattr(client, "answer_callback_query"):
        client.answer_callback_query(callback_query_id)
    return True



def render_listing_card(summary: dict[str, object] | None, *, is_saved: bool, badge: str | None = None) -> str:
    if not summary:
        return ""

    lines: list[str] = []
    display_date_text = _display_date_text(summary)
    room_count = _normalize_room_count_for_ru(_fallback_room_count_text(summary))
    locality = str(summary.get("location_text", "")).strip()
    title_room = room_count or "?"
    title_locality = locality or "неизвестно"
    lines.append(f"<b>Квартира {html.escape(title_room)} комнаты в {html.escape(title_locality)}</b>")
    lines.append("")
    if badge:
        lines.append(_bold_value(badge))
    if is_saved:
        lines.append("⭐ ИЗБРАННОЕ")

    region_text = str(summary.get("region_text", "")).strip()
    if region_text:
        lines.append(f"Регион: {_bold_value(region_text)}")

    price_line = _build_price_line(summary)
    if price_line:
        lines.append(price_line)

    if summary.get("is_private"):
        lines.append("Сдает собственник")
    elif summary.get("is_agency"):
        lines.append("Сдает агентство")

    area_line = _format_area_ru(summary.get("area"))
    if area_line:
        lines.append(f"Площадь: {_bold_value(area_line)}")

    if room_count:
        lines.append(f"Количество комнат: {_bold_value(room_count)}")

    bedroom_line = _build_bedroom_line(summary)
    if bedroom_line:
        lines.append(bedroom_line)

    utilities_line = _build_utilities_line(summary)
    if utilities_line:
        lines.append(utilities_line)

    land_garden_line = _build_land_garden_line(summary)
    if land_garden_line:
        lines.append(land_garden_line)

    url = str(summary.get("url", "")).strip()
    if url:
        lines.append(f'<a href="{html.escape(url, quote=True)}">Смотреть на Nepremicnine.net</a>')
    if display_date_text:
        lines.append("")
        lines.append(f"Дата: {_bold_value(display_date_text)}")

    return "\n".join(lines)



def save_reply_note(message: dict[str, object], db) -> bool:
    reply_to = message.get("reply_to_message") or {}
    chat_id = str((message.get("chat") or {}).get("id", ""))
    message_id = int(reply_to.get("message_id", 0) or 0)
    if not chat_id or not message_id:
        return False
    mapping = db.get_listing_by_message(chat_id, message_id)
    if mapping is None:
        return False
    note_text = str(message.get("text", "")).strip()
    if not note_text:
        return False
    db.add_listing_note(int(mapping["listing_id"]), "note", note_text, None, created_via="telegram")
    return True



def handle_callback_query(callback_query: dict[str, object], client, db) -> None:
    data = str(callback_query.get("data", "")).strip()
    callback_query_id = str(callback_query.get("id", "")).strip()
    message = callback_query.get("message") or {}
    chat_id = str((message.get("chat") or {}).get("id", ""))
    message_id = int(message.get("message_id", 0) or 0)
    action, _, site_id = data.partition(":")
    if not action or not site_id:
        if callback_query_id and hasattr(client, "answer_callback_query"):
            client.answer_callback_query(callback_query_id, text="Неизвестное действие")
        return
    if _handle_settings_callback(callback_query, client, db):
        return
    summary = db.get_listing_summary_by_site_id(site_id)
    if summary is None:
        if callback_query_id and hasattr(client, "answer_callback_query"):
            client.answer_callback_query(callback_query_id, text="Объявление не найдено")
        return
    listing_id = int(summary["listing_id"])

    if action == "save":
        db.set_listing_status(listing_id, "saved")
        refreshed = db.get_listing_summary_by_site_id(site_id)
        if refreshed is not None and hasattr(client, "edit_message_text"):
            client.edit_message_text(
                chat_id,
                message_id,
                _render_listing_with_notes(refreshed, db=db, is_saved=True),
                reply_markup=build_card_keyboard(site_id),
                parse_mode="HTML",
            )
        if callback_query_id and hasattr(client, "answer_callback_query"):
            client.answer_callback_query(callback_query_id, text="Сохранено")
        return

    if action == "reject":
        db.set_listing_status(listing_id, "rejected")
        db.mark_telegram_message_deleted(chat_id, message_id)
        if hasattr(client, "delete_message"):
            client.delete_message(chat_id, message_id)
        if callback_query_id and hasattr(client, "answer_callback_query"):
            client.answer_callback_query(callback_query_id, text="Скрыто")
        return

    if action == "expensive":
        db.set_listing_status(listing_id, "expensive")
        db.mark_telegram_message_deleted(chat_id, message_id)
        if hasattr(client, "delete_message"):
            client.delete_message(chat_id, message_id)
        if callback_query_id and hasattr(client, "answer_callback_query"):
            client.answer_callback_query(callback_query_id, text="Отмечено как дорого")
        return

    if callback_query_id and hasattr(client, "answer_callback_query"):
        client.answer_callback_query(callback_query_id, text="Неизвестное действие")



def handle_note_command(command: str, db) -> str:
    parsed = parse_note_command(command)
    listing = _get_listing_or_raise(db, str(parsed["site_id"]))
    db.set_listing_status(listing.id, str(parsed["status"]))
    db.add_listing_note(
        listing.id,
        str(parsed["status"]),
        str(parsed["note_text"]),
        str(parsed["scheduled_for"]) if parsed["scheduled_for"] is not None else None,
        created_via="telegram",
    )
    scheduled_suffix = f" at {parsed['scheduled_for']}" if parsed["scheduled_for"] else ""
    return f"Saved note for {listing.site_id}: {parsed['status']}{scheduled_suffix}"



def handle_status_command(command: str, db) -> str:
    parsed = parse_status_command(command)
    listing = _get_listing_or_raise(db, parsed["site_id"])
    db.set_listing_status(listing.id, parsed["status"])
    return f"Updated status for {listing.site_id}: {parsed['status']}"



def handle_latest_command(command: str, db) -> str:
    if command.strip() == "Новые":
        limit = MAX_LIST_LIMIT
        mode = "new"
    else:
        limit = _parse_limit(command)
        mode = "new" if command.startswith("/latest") else "realtime"
    items = db.list_recent_listing_candidates(limit=limit, mode=mode)
    if not items:
        return "Новые: пусто" if mode == "new" else "Latest candidates: none"
    return "\n\n".join(_compact_listing_preview(item) for item in items)



def handle_saved_command(command: str, db) -> str:
    limit = MAX_LIST_LIMIT if command.strip() == "Избранное" else _parse_limit(command)
    items = db.list_recent_listing_candidates(limit=limit, mode="saved")
    if not items:
        return "Избранное: пусто"
    return "\n\n".join(_compact_listing_preview(item, db=db) for item in items)


def handle_expensive_command(command: str, db) -> str:
    limit = MAX_LIST_LIMIT if command.strip() == "Дорогие" else _parse_limit(command)
    items = db.list_recent_listing_candidates(limit=limit, mode="expensive")
    if not items:
        return "Дорогие: пусто"
    return "\n\n".join(_compact_listing_preview(item) for item in items)



def handle_maybe_command(command: str, db) -> str:
    limit = _parse_limit(command)
    items = db.list_recent_listing_candidates(limit=limit, mode="maybe")
    if not items:
        return "Maybe queue: none"
    return "\n\n".join(["Maybe queue:", *[_compact_listing_preview(item) for item in items]])



def handle_show_command(command: str, db) -> str:
    _, site_id = command.split(maxsplit=1)
    listing = _get_listing_or_raise(db, site_id)
    summary = db.get_listing_summary_by_site_id(site_id)
    status = db.get_listing_status(listing.id)
    notes = db.list_listing_notes(listing.id)

    lines = [
        f"Listing: {listing.site_id}",
        f"Title: {listing.title}",
        f"Status: {status['status'] if status else 'new'}",
    ]
    if summary is not None:
        lines.extend(
            [
                f"Price: {summary['price_current']}",
                f"Area: {summary['area']}",
                f"Location: {summary['location_text']}",
                f"Bedrooms: {summary['two_bedroom_match']}",
                f"Utilities: {summary['utilities_status']}",
                f"Heating: {summary['heating_type_norm']}",
                f"Realtime: {summary['passes_realtime']}",
                f"URL: {summary['url']}",
            ]
        )
    if not notes:
        lines.append("Notes: none")
        return "\n".join(lines)

    lines.append("Notes:")
    for note in notes:
        schedule_suffix = f" [{note['scheduled_for']}]" if note["scheduled_for"] else ""
        lines.append(f"- {note['note_type']}{schedule_suffix}: {note['note_text']}")
    return "\n".join(lines)



def cleanup_expired_listing_cards(client, db, *, now_iso: str) -> int:
    expired = db.list_expired_telegram_message_mappings(now_iso=now_iso)
    deleted = 0
    for item in expired:
        chat_id = str(item["chat_id"])
        message_id = int(item["telegram_message_id"])
        try:
            if hasattr(client, "delete_message"):
                client.delete_message(chat_id, message_id)
        except httpx.HTTPError:
            pass
        finally:
            db.mark_telegram_message_deleted(chat_id, message_id)
            deleted += 1
    return deleted



def send_listing_cards(client, chat_id: str, db, *, mode: str, now_iso: str) -> int:
    items = db.list_recent_listing_candidates(limit=MAX_LIST_LIMIT, mode=mode)
    if mode == "new":
        settings = db.get_chat_settings(chat_id)
        items = [item for item in items if _matches_chat_filters(item, settings)]
    if not items:
        empty_text_by_mode = {
            "new": "Новые: пусто",
            "saved": "Избранное: пусто",
            "expensive": "Дорогие: пусто",
        }
        empty_text = empty_text_by_mode.get(mode, "Объявления: пусто")
        client.send_message(chat_id, empty_text, reply_markup=build_main_menu_keyboard())
        return 0

    delete_after_at = _delete_after_iso(now_iso)
    sent = 0
    for index, item in enumerate(items):
        if index > 0 and index % TELEGRAM_CARD_BATCH_SIZE == 0:
            time.sleep(TELEGRAM_CARD_BATCH_PAUSE_SECONDS)
        is_saved = str(item.get("status", "")) == "saved"
        text = _render_listing_with_notes(item, db=db if is_saved else None, is_saved=is_saved)
        try:
            message_id = client.send_message(
                chat_id,
                text,
                reply_markup=build_card_keyboard(str(item["site_id"])),
                parse_mode="HTML",
            )
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                time.sleep(TELEGRAM_RETRY_SLEEP_SECONDS)
                try:
                    message_id = client.send_message(
                        chat_id,
                        text,
                        reply_markup=build_card_keyboard(str(item["site_id"])),
                        parse_mode="HTML",
                    )
                except httpx.HTTPStatusError as retry_exc:
                    if retry_exc.response.status_code == 429:
                        break
                    raise
            else:
                raise
        if message_id is not None:
            db.add_telegram_message_mapping(
                chat_id=chat_id,
                telegram_message_id=message_id,
                listing_id=int(item["listing_id"]),
                message_kind="listing_card",
                delete_after_at=delete_after_at,
            )
            sent += 1
    return sent



def send_startup_menu(client, chat_id: str) -> int | None:
    return client.send_message(
        chat_id,
        "Бот запущен. Меню доступно ниже.",
        reply_markup=build_main_menu_keyboard(),
    )


def dispatch_command(command: str, db) -> str:
    stripped = command.strip()
    if stripped == "Новые":
        return handle_latest_command(stripped, db)
    if stripped == "Избранное":
        return handle_saved_command(stripped, db)
    if stripped == "Дорогие":
        return handle_expensive_command(stripped, db)
    if stripped == "Настройки":
        return "Настройки доступны через кнопку в чате."
    if command.startswith("/latest"):
        return handle_latest_command(command, db)
    if command.startswith("/saved"):
        return handle_saved_command(command, db)
    if command.startswith("/expensive"):
        return handle_expensive_command(command, db)
    if command.startswith("/maybe"):
        return handle_maybe_command(command, db)
    if command.startswith("/show"):
        return handle_show_command(command, db)
    if command.startswith("/status"):
        return handle_status_command(command, db)
    if command.startswith("/note"):
        return handle_note_command(command, db)
    if command.startswith("/help") or command.startswith("/start"):
        return build_help_message()
    return build_help_message()



def run_command_bot(client, allowed_chat_id: str, db, *, once: bool = False, offset: int | None = None, timeout: int = 30):
    next_offset = offset
    try:
        send_startup_menu(client, str(allowed_chat_id))
    except httpx.HTTPError:
        pass
    while True:
        try:
            updates = client.get_updates(offset=next_offset, timeout=timeout)
        except httpx.HTTPError:
            if once:
                return next_offset
            time.sleep(TELEGRAM_RETRY_SLEEP_SECONDS)
            continue
        now_iso = _now_iso()
        cleanup_expired_listing_cards(client, db, now_iso=now_iso)
        for update in updates:
            update_id = int(update.get("update_id", 0))
            if next_offset is None or update_id + 1 > next_offset:
                next_offset = update_id + 1
            message = update.get("message") or update.get("edited_message")
            if isinstance(message, dict):
                chat_id = str(((message.get("chat") or {}).get("id", "")))
                if chat_id != str(allowed_chat_id):
                    continue
                if save_reply_note(message, db):
                    continue
                text = str(message.get("text") or "").strip()
                if not text:
                    continue
                try:
                    pending_settings_handled = _handle_pending_settings_input(chat_id, text, client, db)
                except httpx.HTTPError:
                    break
                if pending_settings_handled:
                    continue
                if text == "Новые":
                    send_listing_cards(client, chat_id, db, mode="new", now_iso=now_iso)
                    continue
                if text == "Избранное":
                    send_listing_cards(client, chat_id, db, mode="saved", now_iso=now_iso)
                    continue
                if text == "Дорогие":
                    send_listing_cards(client, chat_id, db, mode="expensive", now_iso=now_iso)
                    continue
                if text == "Настройки":
                    settings_text, settings_keyboard = handle_settings_command(chat_id, db)
                    try:
                        client.send_message(chat_id, settings_text, reply_markup=settings_keyboard)
                    except httpx.HTTPError:
                        break
                    continue
                try:
                    response = dispatch_command(text, db)
                except Exception as exc:
                    response = f"Error: {exc}"
                reply_markup = build_main_menu_keyboard() if text.startswith("/help") or text.startswith("/start") else None
                try:
                    client.send_message(chat_id, response, reply_markup=reply_markup)
                except httpx.HTTPError:
                    break
                continue

            callback_query = update.get("callback_query")
            if isinstance(callback_query, dict):
                callback_message = callback_query.get("message") or {}
                chat_id = str(((callback_message.get("chat") or {}).get("id", "")))
                if chat_id != str(allowed_chat_id):
                    continue
                try:
                    handle_callback_query(callback_query, client, db)
                except httpx.HTTPError:
                    break
        if once:
            return next_offset
