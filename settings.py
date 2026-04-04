from pydantic_settings import BaseSettings
from pydantic import Field


class AppSettings(BaseSettings):
    bot_token: str = Field(default="......")
    gemini_api_key: str = Field(default="......")
    admin_ids: list[int] = Field(default_factory=list)
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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


def get_settings() -> AppSettings:
    return AppSettings()
