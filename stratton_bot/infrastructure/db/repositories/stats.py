from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from stratton_bot.domain.entities import StatsSummary
from stratton_bot.infrastructure.db.models import NdaRecordModel, SubmissionModel, TestingRecordModel, UserModel


class SqlAlchemyStatsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_summary(self) -> StatsSummary:
        async def count(model, *filters) -> int:
            query = select(func.count()).select_from(model)
            for condition in filters:
                query = query.where(condition)
            return (await self._session.execute(query)).scalar() or 0

        return StatsSummary(
            total_users=await count(UserModel),
            scheduled=await count(TestingRecordModel, TestingRecordModel.status == "scheduled"),
            in_progress=await count(TestingRecordModel, TestingRecordModel.status == "in_progress"),
            submitted=await count(TestingRecordModel, TestingRecordModel.status == "submitted"),
            expired=await count(TestingRecordModel, TestingRecordModel.status == "expired"),
            accepted=await count(SubmissionModel, SubmissionModel.review_result == "accepted"),
            rejected=await count(SubmissionModel, SubmissionModel.review_result == "rejected"),
            pending_reviews=await count(SubmissionModel, SubmissionModel.reviewed.is_(False)),
            nda_completed=await count(NdaRecordModel, NdaRecordModel.status == "completed"),
        )
