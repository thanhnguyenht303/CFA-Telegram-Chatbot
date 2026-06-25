from __future__ import annotations

import os
from datetime import time
from functools import lru_cache
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv
from pydantic import BaseModel, Field, field_validator


def _parse_bool(value: str | None, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _parse_time(value: str | None, default: str) -> time:
    raw = (value or default).strip()
    hour, minute = raw.split(":", 1)
    return time(hour=int(hour), minute=int(minute))


def _parse_admin_ids(value: str | None) -> list[int]:
    if not value:
        return []
    ids: list[int] = []
    for item in value.split(","):
        item = item.strip()
        if item:
            ids.append(int(item))
    return ids


class Settings(BaseModel):
    telegram_bot_token: str | None = None
    database_url: str = "sqlite:///./data/cfa_vocab.db"
    openai_api_key: str | None = None
    openai_research_model: str = "gpt-5.4-mini"
    openai_timeout_seconds: float = 60.0
    webhook_secret: str | None = None
    admin_user_ids: list[int] = Field(default_factory=list)
    admin_api_key: str | None = None
    default_timezone: str = "America/Chicago"
    default_daily_send_time: time = time(7, 30)
    default_mini_review_time: time = time(21, 40)
    default_weekly_quiz_time: time = time(9, 0)
    default_weekly_recap_time: time = time(18, 30)
    log_level: str = "INFO"
    polling: bool = True
    webhook_url: str | None = None

    @field_validator("default_timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown timezone: {value}") from exc
        return value

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(override=True)
        return cls(
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN") or None,
            database_url=os.getenv("DATABASE_URL", "sqlite:///./data/cfa_vocab.db"),
            openai_api_key=os.getenv("OPENAI_API_KEY") or None,
            openai_research_model=os.getenv("OPENAI_RESEARCH_MODEL", "gpt-5.4-mini"),
            openai_timeout_seconds=float(os.getenv("OPENAI_TIMEOUT_SECONDS", "60")),
            webhook_secret=os.getenv("WEBHOOK_SECRET") or None,
            admin_user_ids=_parse_admin_ids(os.getenv("ADMIN_USER_IDS")),
            admin_api_key=os.getenv("ADMIN_API_KEY") or None,
            default_timezone=os.getenv("DEFAULT_TIMEZONE", "America/Chicago"),
            default_daily_send_time=_parse_time(os.getenv("DEFAULT_DAILY_SEND_TIME"), "07:30"),
            default_mini_review_time=_parse_time(os.getenv("DEFAULT_MINI_REVIEW_TIME"), "21:40"),
            default_weekly_quiz_time=_parse_time(os.getenv("DEFAULT_WEEKLY_QUIZ_TIME"), "09:00"),
            default_weekly_recap_time=_parse_time(
                os.getenv("DEFAULT_WEEKLY_RECAP_TIME"), "18:30"
            ),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            polling=_parse_bool(os.getenv("POLLING"), True),
            webhook_url=os.getenv("WEBHOOK_URL") or None,
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()
