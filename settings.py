import json

from pydantic import AliasChoices, Field, computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Settings from .env. ADMIN_IDS: comma-separated IDs or JSON array, e.g. 123,456 or [123,456]."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    bot_token: str = Field(default="......")
    gemini_api_key: str = Field(default="......")
    # Stored as str so pydantic-settings does not json.loads() the env value (breaks on "1,2,3").
    admin_ids_csv: str = Field(
        default="",
        validation_alias=AliasChoices("ADMIN_IDS", "admin_ids_csv"),
    )
    group_invite_link: str = Field(default=".........")
    database_url: str = Field(default="sqlite+aiosqlite:///data/stratton_bot.db")
    timezone: str = Field(default="Asia/Almaty")
    slot_start_hour: int = Field(default=7)
    slot_end_hour: int = Field(default=23)
    days_ahead: int = Field(default=30)
    task_hours: int = Field(default=3)
    max_video_size_bytes: int = Field(default=10 * 1024 * 1024)
    max_retry_attempts: int = Field(default=3)
    remind_before_minutes: int = Field(default=15)
    backup_dir: str = Field(default="data/backups")

    @computed_field
    @property
    def admin_ids(self) -> list[int]:
        s = self.admin_ids_csv.strip()
        if not s:
            return []
        if s.startswith("["):
            try:
                data = json.loads(s)
                if isinstance(data, list):
                    return [int(x) for x in data]
            except (json.JSONDecodeError, ValueError, TypeError):
                pass
            return []
        return [int(x.strip()) for x in s.split(",") if x.strip()]


def get_settings() -> AppSettings:
    return AppSettings()
