from __future__ import annotations

from datetime import datetime

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from stratton_bot.domain.entities import ActiveTesting
from stratton_bot.infrastructure.db.mappers import to_testing_entity
from stratton_bot.infrastructure.db.models import TestingRecordModel, TimeSlotModel


class SqlAlchemyTestingRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, user_id: int, slot_id: int, task_variant: int) -> ActiveTesting:
        record = TestingRecordModel(user_id=user_id, slot_id=slot_id, task_variant=task_variant)
        self._session.add(record)
        await self._session.flush()
        slot = await self._session.get(TimeSlotModel, slot_id)
        if slot is None:
            raise ValueError(f"Slot {slot_id} not found after create")
        return to_testing_entity(record, slot)

    async def get_active_by_user(self, user_id: int) -> ActiveTesting | None:
        result = await self._session.execute(
            select(TestingRecordModel, TimeSlotModel)
            .join(TimeSlotModel, TestingRecordModel.slot_id == TimeSlotModel.id)
            .where(
                and_(
                    TestingRecordModel.user_id == user_id,
                    TestingRecordModel.status.in_(("scheduled", "in_progress")),
                )
            )
            .order_by(TestingRecordModel.created_at.desc())
            .limit(1)
        )
        row = result.first()
        if row is None:
            return None
        testing, slot = row
        return to_testing_entity(testing, slot)

    async def get_by_id(self, testing_id: int) -> ActiveTesting | None:
        result = await self._session.execute(
            select(TestingRecordModel, TimeSlotModel)
            .join(TimeSlotModel, TestingRecordModel.slot_id == TimeSlotModel.id)
            .where(TestingRecordModel.id == testing_id)
        )
        row = result.first()
        if row is None:
            return None
        testing, slot = row
        return to_testing_entity(testing, slot)

    async def set_status(self, testing_id: int, status: str) -> None:
        record = await self._session.get(TestingRecordModel, testing_id)
        if record:
            record.status = status

    async def submit_active(self, user_id: int) -> None:
        result = await self._session.execute(
            select(TestingRecordModel)
            .where(
                and_(
                    TestingRecordModel.user_id == user_id,
                    TestingRecordModel.status.in_(("scheduled", "in_progress")),
                )
            )
            .order_by(TestingRecordModel.created_at.desc())
            .limit(1)
        )
        record = result.scalar_one_or_none()
        if record:
            record.status = "submitted"
            record.submitted_at = datetime.utcnow()

    async def list_open(self) -> list[ActiveTesting]:
        result = await self._session.execute(
            select(TestingRecordModel, TimeSlotModel)
            .join(TimeSlotModel, TestingRecordModel.slot_id == TimeSlotModel.id)
            .where(TestingRecordModel.status.in_(("scheduled", "in_progress")))
        )
        return [to_testing_entity(testing, slot) for testing, slot in result]
