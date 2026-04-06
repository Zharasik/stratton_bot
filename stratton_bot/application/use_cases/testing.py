from __future__ import annotations

from datetime import datetime

from stratton_bot.application.ports.uow import UnitOfWorkFactory
from stratton_bot.application.services.task_catalog import TaskCatalog
from stratton_bot.domain.entities import ActiveTesting, TimeSlot
from stratton_bot.domain.exceptions import ConflictError, NotFoundError, ValidationError
from stratton_bot.infrastructure.config.settings import AppConfig


class TestingUseCase:
    def __init__(self, uow_factory: UnitOfWorkFactory, task_catalog: TaskCatalog, config: AppConfig) -> None:
        self._uow_factory = uow_factory
        self._task_catalog = task_catalog
        self._config = config

    async def get_active(self, user_id: int) -> ActiveTesting | None:
        async with self._uow_factory() as uow:
            return await uow.testings.get_active_by_user(user_id)

    async def list_slots_for_date(self, user_id: int, date_str: str, now: datetime) -> list[TimeSlot]:
        async with self._uow_factory() as uow:
            active_testing = await uow.testings.get_active_by_user(user_id)
            if active_testing:
                raise ConflictError("User already has active testing")
            await uow.slots.ensure_for_date(date_str, self._config.slot_start_hour, self._config.slot_end_hour)
            slots = await uow.slots.list_by_date(date_str)
            await uow.commit()
        if date_str == now.strftime("%Y-%m-%d"):
            return [slot for slot in slots if int(slot.slot_start.split(":")[0]) >= now.hour + 1]
        return slots

    async def confirm_slot(self, user_id: int, slot_id: int) -> ActiveTesting:
        async with self._uow_factory() as uow:
            active_testing = await uow.testings.get_active_by_user(user_id)
            if active_testing:
                raise ConflictError("Testing already scheduled")
            user = await uow.users.get_by_id(user_id)
            if user is None:
                raise NotFoundError(f"User {user_id} not found")
            if user.retry_count >= self._config.max_retry_attempts:
                raise ValidationError("Retry limit exceeded")
            reserved = await uow.slots.book(slot_id, user_id)
            if not reserved:
                raise ConflictError("Slot is already booked")
            variant = self._task_catalog.get_variant_number(user_id)
            testing = await uow.testings.create(user_id=user_id, slot_id=slot_id, task_variant=variant)
            await uow.users.set_status(user_id, "testing_scheduled")
            await uow.users.increment_retry(user_id)
            await uow.commit()
        return testing

    async def get_slot(self, slot_id: int) -> TimeSlot | None:
        async with self._uow_factory() as uow:
            return await uow.slots.get_by_id(slot_id)

    async def cancel(self, user_id: int) -> None:
        async with self._uow_factory() as uow:
            active_testing = await uow.testings.get_active_by_user(user_id)
            if active_testing is None:
                raise NotFoundError("Active testing not found")
            await uow.testings.set_status(active_testing.id, "cancelled")
            await uow.slots.release(active_testing.slot_id)
            await uow.users.set_status(user_id, "cancelled")
            await uow.commit()

    def is_task_available(self, testing: ActiveTesting) -> bool:
        return self._task_catalog.is_within_window(
            testing.slot_date,
            testing.slot_start,
            self._config.task_hours,
            self._config.timezone,
        )

    def get_deadline(self, testing: ActiveTesting) -> str:
        return self._task_catalog.get_deadline(testing.slot_date, testing.slot_start, self._config.task_hours)

    def get_remaining_minutes(self, testing: ActiveTesting) -> int:
        return self._task_catalog.get_remaining_minutes(
            testing.slot_date,
            testing.slot_start,
            self._config.task_hours,
            self._config.timezone,
        )
