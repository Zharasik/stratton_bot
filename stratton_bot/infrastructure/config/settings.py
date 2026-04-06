from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from stratton_bot.domain.exceptions import ConfigurationError

load_dotenv()


def _parse_int(value: str | None, default: int) -> int:
    if value in (None, ""):
        return default
    return int(value)


def _parse_admin_ids(value: str | None) -> list[int]:
    if not value:
        return []
    return [int(item.strip()) for item in value.split(",") if item.strip()]


@dataclass(slots=True)
class AppConfig:
    bot_token: str
    gemini_api_key: str
    admin_ids: list[int]
    group_invite_link: str
    database_url: str
    timezone: str
    slot_start_hour: int
    slot_end_hour: int
    days_ahead: int
    task_hours: int
    max_video_size_bytes: int
    max_retry_attempts: int
    remind_before_minutes: int
    backup_dir: Path
    data_dir: Path
    locales_dir: Path
    static_dir: Path
    default_locale: str = "ru"

    @classmethod
    def from_env(cls) -> "AppConfig":
        data_dir = Path(os.getenv("DATA_DIR", "data"))
        return cls(
            bot_token=os.getenv("BOT_TOKEN", "").strip(),
            gemini_api_key=os.getenv("GEMINI_API_KEY", "").strip(),
            admin_ids=_parse_admin_ids(os.getenv("ADMIN_IDS")),
            group_invite_link=os.getenv("GROUP_INVITE_LINK", "").strip(),
            database_url=os.getenv("DATABASE_URL", "sqlite+aiosqlite:///data/stratton_bot.db").strip(),
            timezone=os.getenv("TIMEZONE", "Asia/Almaty").strip(),
            slot_start_hour=_parse_int(os.getenv("SLOT_START_HOUR"), 7),
            slot_end_hour=_parse_int(os.getenv("SLOT_END_HOUR"), 23),
            days_ahead=_parse_int(os.getenv("DAYS_AHEAD"), 30),
            task_hours=_parse_int(os.getenv("TASK_HOURS"), 3),
            max_video_size_bytes=_parse_int(os.getenv("MAX_VIDEO_SIZE_BYTES"), 10 * 1024 * 1024),
            max_retry_attempts=_parse_int(os.getenv("MAX_RETRY_ATTEMPTS"), 3),
            remind_before_minutes=_parse_int(os.getenv("REMIND_BEFORE_MINUTES"), 15),
            backup_dir=Path(os.getenv("BACKUP_DIR", "data/backups")),
            data_dir=data_dir,
            locales_dir=Path(os.getenv("LOCALES_DIR", "locales")),
            static_dir=Path(os.getenv("STATIC_DIR", "static")),
            default_locale=os.getenv("DEFAULT_LOCALE", "ru").strip() or "ru",
        )

    def validate(self) -> None:
        if not self.bot_token:
            raise ConfigurationError("BOT_TOKEN is required")
        if not self.gemini_api_key:
            raise ConfigurationError("GEMINI_API_KEY is required")
