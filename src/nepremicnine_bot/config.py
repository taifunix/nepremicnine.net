import json
from pathlib import Path

from pydantic import AliasChoices, BaseModel, Field
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
    utilities_included_positive: list[str] = Field(
        default_factory=lambda: ["stroski vkljuceni", "utilities included"]
    )
    utilities_included_partial: list[str] = Field(default_factory=lambda: ["internet included"])
    utilities_separate_negative: list[str] = Field(
        default_factory=lambda: ["stroski niso vkljuceni", "utilities excluded"]
    )


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="NEPREMICNINE_", extra="ignore")

    bot_token: str = Field(validation_alias=AliasChoices("NEPREMICNINE_BOT_TOKEN", "BOT_TOKEN"))
    chat_id: str = Field(validation_alias=AliasChoices("NEPREMICNINE_CHAT_ID", "CHAT_ID"))
    db_path: str = Field(validation_alias=AliasChoices("NEPREMICNINE_DB_PATH", "DB_PATH"))
    poll_minutes: int = Field(
        default=5,
        validation_alias=AliasChoices("NEPREMICNINE_POLL_MINUTES", "POLL_MINUTES"),
    )
    fetch_mode: str = Field(
        default="browser",
        validation_alias=AliasChoices("NEPREMICNINE_FETCH_MODE", "FETCH_MODE"),
    )
    search_sources_file: str | None = Field(
        default=None,
        validation_alias=AliasChoices("NEPREMICNINE_SEARCH_SOURCES_FILE", "SEARCH_SOURCES_FILE"),
    )
    search_sources: list[SearchSource] = Field(default_factory=list)
    rules: RuleSet = Field(default_factory=RuleSet)

    @property
    def telegram_bot_token(self) -> str:
        return self.bot_token

    @property
    def telegram_chat_id(self) -> str:
        return self.chat_id

    def load_search_sources(self) -> list[SearchSource]:
        if self.search_sources:
            return self.search_sources
        if not self.search_sources_file:
            return []
        data = json.loads(Path(self.search_sources_file).read_text(encoding="utf-8"))
        return [SearchSource.model_validate(item) for item in data]
