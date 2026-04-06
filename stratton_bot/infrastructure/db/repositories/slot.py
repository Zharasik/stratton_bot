from __future__ import annotations

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from stratton_bot.domain.entities import BookedSlotDetail, NotificationTarget, ReminderTarget, TimeSlot
from stratton_bot.infrastructure.db.mappers import to_booked_detail, to_slot_entity
from stratton_bot.infrastructure.db.models import TestingRecordModel, TimeSlotModel, UserModel


class SqlAlchemySlotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def ensure_for_date(self, date_str: str, start_hour: int, end_hour: int) -> None:
        result = await self._session.execute(
            select(func.count()).select_from(TimeSlotModel).where(TimeSlotModel.slot_date == date_str)
        )
        if (result.scalar() or 0) > 0:
            return
        for hour in range(start_hour, end_hour):
            self._session.add(
                TimeSlotModel(
                    slot_date=date_str,
                    slot_start=f"{hour:02d}:00",
                    slot_end=f"{hour + 1:02d}:00",
                )
            )

    async def list_by_date(self, date_str: str) -> list[TimeSlot]:
        result = await self._session.execute(
            select(TimeSlotModel)
            .where(TimeSlotModel.slot_date == date_str)
            .order_by(TimeSlotModel.slot_start)
        )
        return [to_slot_entity(slot) for slot in result.scalars()]

    async def get_by_id(self, slot_id: int) -> TimeSlot | None:
        slot = await self._session.get(TimeSlotModel, slot_id)
        return to_slot_entity(slot) if slot else None

    async def book(self, slot_id: int, user_id: int) -> bool:
        slot = await self._session.get(TimeSlotModel, slot_id, with_for_update=True)
        if slot is None or slot.booked_by is not None:
            return False
        slot.booked_by = user_id
        return True

    async def release(self, slot_id: int) -> None:
        slot = await self._session.get(TimeSlotModel, slot_id)
        if slot is None:
            return
        slot.booked_by = None
        slot.notified = False
        slot.reminded = False

    async def list_booked_dates(self) -> list[dict[str, int | str]]:
        result = await self._session.execute(
            select(TimeSlotModel.slot_date, func.count().label("booked_count"))
            .where(TimeSlotModel.booked_by.is_not(None))
            .group_by(TimeSlotModel.slot_date)
            .order_by(TimeSlotModel.slot_date)
        )
        return [{"slot_date": row[0], "booked_count": row[1]} for row in result]

    async def list_booked_details(self, date_str: str) -> list[BookedSlotDetail]:
        result = await self._session.execute(
            select(TimeSlotModel, UserModel, TestingRecordModel)
            .join(UserModel, TimeSlotModel.booked_by == UserModel.user_id)
            .outerjoin(
                TestingRecordModel,
                and_(
                    TestingRecordModel.slot_id == TimeSlotModel.id,
                    TestingRecordModel.user_id == UserModel.user_id,
                ),
            )
            .where(and_(TimeSlotModel.slot_date == date_str, TimeSlotModel.booked_by.is_not(None)))
            .order_by(TimeSlotModel.slot_start)
        )
        return [to_booked_detail(slot, user, testing) for slot, user, testing in result]

    async def list_for_reminder(self, date_str: str, hour_str: str) -> list[ReminderTarget]:
        result = await self._session.execute(
            select(TimeSlotModel, TestingRecordModel)
            .join(TestingRecordModel, TimeSlotModel.id == TestingRecordModel.slot_id)
            .where(
                and_(
                    TimeSlotModel.slot_date == date_str,
                    TimeSlotModel.slot_start == hour_str,
                    TimeSlotModel.booked_by.is_not(None),
                    TimeSlotModel.reminded.is_(False),
                    TestingRecordModel.status == "scheduled",
                )
            )
        )
        return [ReminderTarget(slot_id=slot.id, user_id=testing.user_id) for slot, testing in result]

    async def mark_reminded(self, slot_id: int) -> None:
        slot = await self._session.get(TimeSlotModel, slot_id)
        if slot:
            slot.reminded = True

    async def list_for_notification(self, date_str: str, hour_str: str) -> list[NotificationTarget]:
        result = await self._session.execute(
            select(TimeSlotModel, TestingRecordModel)
            .join(TestingRecordModel, TimeSlotModel.id == TestingRecordModel.slot_id)
            .where(
                and_(
                    TimeSlotModel.slot_date == date_str,
                    TimeSlotModel.slot_start == hour_str,
                    TimeSlotModel.booked_by.is_not(None),
                    TimeSlotModel.notified.is_(False),
                    TestingRecordModel.status == "scheduled",
                )
            )
        )
        return [
            NotificationTarget(slot_id=slot.id, user_id=testing.user_id, testing_id=testing.id)
            for slot, testing in result
        ]

    async def mark_notified(self, slot_id: int) -> None:
        slot = await self._session.get(TimeSlotModel, slot_id)
        if slot:
            slot.notified = True
