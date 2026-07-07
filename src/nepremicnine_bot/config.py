import json
from pathlib import Path

from pydantic import AliasChoices, BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SearchSource(BaseModel):
    name: str
    url: str
    full_url: str | None = None
    daily_url: str | None = None
    enabled: bool = True
    mode: list[str] = Field(default_factory=lambda: ["realtime-private"])
    publication_window_strategy: str = "today"
    location_blacklist: list[str] = Field(default_factory=list)

    def model_post_init(self, __context) -> None:
        if self.full_url is None:
            self.full_url = self.url
        if self.daily_url is None:
            self.daily_url = self._build_24h_variant(self.url)

    @staticmethod
    def _build_24h_variant(url: str) -> str:
        prefix = "https://www.nepremicnine.net/"
        if not url.startswith(prefix):
            return url
        suffix = url[len(prefix):]
        if suffix.startswith("24ur/"):
            return url
        return f"{prefix}24ur/{suffix}"


class RuleSet(BaseModel):
    two_bedroom_positive: list[str] = Field(default_factory=lambda: ["2 spalnici", "two bedrooms"])
    two_bedroom_negative: list[str] = Field(default_factory=lambda: ["garsonjera", "enosobno"])
    utilities_included_positive: list[str] = Field(
        default_factory=lambda: ["stroski vkljuceni", "utilities included"]
    )
    utilities_included_partial: list[str] = Field(default_factory=lambda: ["internet included"])
    utilities_separate_negative: list[str] = Field(
        default_factory=lambda: ["stroski niso vkljuceni", "utilities excluded"]
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NEPREMICNINE_",
        extra="ignore",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    bot_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices("NEPREMICNINE_BOT_TOKEN", "BOT_TOKEN"),
    )
    chat_id: str | None = Field(
        default=None,
        validation_alias=AliasChoices("NEPREMICNINE_CHAT_ID", "CHAT_ID"),
    )
    db_path: str = Field(
        default="./data/app.db",
        validation_alias=AliasChoices("NEPREMICNINE_DB_PATH", "DB_PATH"),
    )
    poll_minutes: int = Field(
        default=5,
        validation_alias=AliasChoices("NEPREMICNINE_POLL_MINUTES", "POLL_MINUTES"),
    )
    fetch_mode: str = Field(
        default="browser",
        validation_alias=AliasChoices("NEPREMICNINE_FETCH_MODE", "FETCH_MODE"),
    )
    browser_user_data_dir: str = Field(
        default="./data/browser-profile",
        validation_alias=AliasChoices("NEPREMICNINE_BROWSER_USER_DATA_DIR", "BROWSER_USER_DATA_DIR"),
    )
    browser_headless: bool = Field(
        default=True,
        validation_alias=AliasChoices("NEPREMICNINE_BROWSER_HEADLESS", "BROWSER_HEADLESS"),
    )
    browser_channel: str = Field(
        default="chrome",
        validation_alias=AliasChoices("NEPREMICNINE_BROWSER_CHANNEL", "BROWSER_CHANNEL"),
    )
    browser_proxy: str | None = Field(
        default=None,
        validation_alias=AliasChoices("NEPREMICNINE_BROWSER_PROXY", "BROWSER_PROXY"),
    )
    browser_cookies_path: str = Field(
        default="./data/session-cookies.json",
        validation_alias=AliasChoices("NEPREMICNINE_BROWSER_COOKIES_PATH", "BROWSER_COOKIES_PATH"),
    )
    browser_storage_state_path: str = Field(
        default="./data/storage-state.json",
        validation_alias=AliasChoices(
            "NEPREMICNINE_BROWSER_STORAGE_STATE_PATH",
            "BROWSER_STORAGE_STATE_PATH",
        ),
    )
    search_sources_file: str | None = Field(
        default=None,
        validation_alias=AliasChoices("NEPREMICNINE_SEARCH_SOURCES_FILE", "SEARCH_SOURCES_FILE"),
    )
    search_sources: list[SearchSource] = Field(default_factory=list)
    audit_watch_ids: list[str] = Field(
        default_factory=lambda: ["7381374", "7381383", "7381386", "7381941", "7381963", "7382002"]
    )
    rules: RuleSet = Field(default_factory=RuleSet)

    def model_post_init(self, __context) -> None:
        dotenv_path = self._resolve_env_file_path(__context)
        if not dotenv_path:
            return
        dotenv_values = self._load_raw_dotenv(dotenv_path)
        if not self.bot_token:
            self.bot_token = dotenv_values.get("NEPREMICNINE_BOT_TOKEN") or dotenv_values.get("BOT_TOKEN")
        if not self.chat_id:
            self.chat_id = dotenv_values.get("NEPREMICNINE_CHAT_ID") or dotenv_values.get("CHAT_ID")

    @staticmethod
    def _resolve_env_file_path(context) -> Path | None:
        if isinstance(context, dict) and context.get("_env_file"):
            return Path(str(context["_env_file"]))
        default_path = Path(".env")
        return default_path if default_path.exists() else None

    @staticmethod
    def _load_raw_dotenv(path: Path) -> dict[str, str]:
        values: dict[str, str] = {}
        if not path.exists():
            return values
        for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip().strip('"').strip("'")
        return values

    @property
    def telegram_bot_token(self) -> str:
        if not self.bot_token:
            raise ValueError("Telegram bot token is required for polling commands")
        return self.bot_token

    @property
    def telegram_chat_id(self) -> str:
        if not self.chat_id:
            raise ValueError("Telegram chat id is required for polling commands")
        return self.chat_id

    def load_search_sources(self) -> list[SearchSource]:
        if self.search_sources:
            return self.search_sources
        if not self.search_sources_file:
            return []
        data = json.loads(Path(self.search_sources_file).read_text(encoding="utf-8"))
        return [SearchSource.model_validate(item) for item in data]
