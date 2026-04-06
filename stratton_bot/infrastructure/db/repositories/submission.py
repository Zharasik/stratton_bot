from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from stratton_bot.domain.entities import SubmissionRecord
from stratton_bot.infrastructure.db.mappers import to_submission_entity
from stratton_bot.infrastructure.db.models import SubmissionModel, UserModel


class SqlAlchemySubmissionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        user_id: int,
        testing_id: int | None,
        file_id: str | None,
        file_type: str | None,
        link: str | None,
        file_size: int | None,
    ) -> SubmissionRecord:
        submission = SubmissionModel(
            user_id=user_id,
            testing_id=testing_id,
            file_id=file_id,
            file_type=file_type,
            link=link,
            file_size=file_size,
        )
        self._session.add(submission)
        await self._session.flush()
        return to_submission_entity(submission)

    async def list_pending(self) -> list[SubmissionRecord]:
        result = await self._session.execute(
            select(SubmissionModel, UserModel)
            .join(UserModel, SubmissionModel.user_id == UserModel.user_id)
            .where(SubmissionModel.reviewed.is_(False))
            .order_by(SubmissionModel.submitted_at.desc())
        )
        return [to_submission_entity(submission, user) for submission, user in result]

    async def get_by_id(self, submission_id: int) -> SubmissionRecord | None:
        result = await self._session.execute(
            select(SubmissionModel, UserModel)
            .join(UserModel, SubmissionModel.user_id == UserModel.user_id)
            .where(SubmissionModel.id == submission_id)
        )
        row = result.first()
        if row is None:
            return None
        submission, user = row
        return to_submission_entity(submission, user)

    async def review(self, submission_id: int, decision: str, reviewer_id: int) -> None:
        submission = await self._session.get(SubmissionModel, submission_id)
        if submission:
            submission.reviewed = True
            submission.review_result = decision
            submission.reviewer_id = reviewer_id
