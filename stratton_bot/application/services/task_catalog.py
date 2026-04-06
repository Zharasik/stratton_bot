from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo


class TaskCatalog:
    def __init__(self, variants_count: int = 10) -> None:
        self._variants_count = variants_count

    def get_variant_number(self, user_id: int) -> int:
        return (user_id % self._variants_count) + 1

    def is_within_window(self, slot_date: str, slot_start: str, task_hours: int, timezone: str) -> bool:
        now = datetime.now(ZoneInfo(timezone))
        start = datetime.strptime(f"{slot_date} {slot_start}", "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo(timezone))
        return start <= now <= start + timedelta(hours=task_hours)

    def get_deadline(self, slot_date: str, slot_start: str, task_hours: int) -> str:
        start = datetime.strptime(f"{slot_date} {slot_start}", "%Y-%m-%d %H:%M")
        return (start + timedelta(hours=task_hours)).strftime("%H:%M")

    def get_remaining_minutes(self, slot_date: str, slot_start: str, task_hours: int, timezone: str) -> int:
        now = datetime.now(ZoneInfo(timezone))
        start = datetime.strptime(f"{slot_date} {slot_start}", "%Y-%m-%d %H:%M").replace(tzinfo=ZoneInfo(timezone))
        end = start + timedelta(hours=task_hours)
        remaining = end - now
        return max(0, int(remaining.total_seconds() // 60))
