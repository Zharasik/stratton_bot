from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from stratton_bot.application.ports.uow import UnitOfWorkFactory
from stratton_bot.application.services.task_catalog import TaskCatalog
from stratton_bot.domain.entities import NotificationTarget, ReminderTarget
from stratton_bot.infrastructure.config.settings import AppConfig


class SchedulerUseCase:
    def __init__(self, uow_factory: UnitOfWorkFactory, config: AppConfig, task_catalog: TaskCatalog) -> None:
        self._uow_factory = uow_factory
        self._config = config
        self._task_catalog = task_catalog

    async def collect_reminders(self) -> list[ReminderTarget]:
        timezone = ZoneInfo(self._config.timezone)
        now = datetime.now(timezone)
        remind_at = now + timedelta(minutes=self._config.remind_before_minutes)
        if remind_at.date() != now.date():
            return []
        async with self._uow_factory() as uow:
            targets = await uow.slots.list_for_reminder(now.strftime("%Y-%m-%d"), f"{remind_at.hour:02d}:00")
            for target in targets:
                await uow.slots.mark_reminded(target.slot_id)
            await uow.commit()
        return targets

    async def collect_notifications(self) -> list[NotificationTarget]:
        timezone = ZoneInfo(self._config.timezone)
        now = datetime.now(timezone)
        async with self._uow_factory() as uow:
            targets = await uow.slots.list_for_notification(now.strftime("%Y-%m-%d"), f"{now.hour:02d}:00")
            for target in targets:
                await uow.testings.set_status(target.testing_id, "in_progress")
                await uow.slots.mark_notified(target.slot_id)
            await uow.commit()
        return targets

    async def expire_old(self) -> list[int]:
        timezone = ZoneInfo(self._config.timezone)
        now = datetime.now(timezone)
        expired_user_ids: list[int] = []
        async with self._uow_factory() as uow:
            open_testings = await uow.testings.list_open()
            for testing in open_testings:
                slot_start = datetime.strptime(
                    f"{testing.slot_date} {testing.slot_start}",
                    "%Y-%m-%d %H:%M",
                ).replace(tzinfo=timezone)
                if now <= slot_start + timedelta(hours=self._config.task_hours):
                    continue
                await uow.testings.set_status(testing.id, "expired")
                await uow.slots.release(testing.slot_id)
                expired_user_ids.append(testing.user_id)
            await uow.commit()
        return expired_user_ids

    def get_deadline(self, slot_date: str, slot_start: str) -> str:
        return self._task_catalog.get_deadline(slot_date, slot_start, self._config.task_hours)

    def get_variant_number(self, user_id: int) -> int:
        return self._task_catalog.get_variant_number(user_id)
