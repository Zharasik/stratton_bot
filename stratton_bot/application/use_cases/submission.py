from __future__ import annotations

from stratton_bot.application.ports.uow import UnitOfWorkFactory
from stratton_bot.domain.entities import ReviewOutcome, SubmissionRecord
from stratton_bot.domain.exceptions import NotFoundError


class SubmissionUseCase:
    def __init__(self, uow_factory: UnitOfWorkFactory) -> None:
        self._uow_factory = uow_factory

    async def submit_file(
        self,
        *,
        user_id: int,
        file_id: str,
        file_type: str,
        file_size: int | None,
    ) -> SubmissionRecord:
        async with self._uow_factory() as uow:
            active_testing = await uow.testings.get_active_by_user(user_id)
            submission = await uow.submissions.create(
                user_id=user_id,
                testing_id=active_testing.id if active_testing else None,
                file_id=file_id,
                file_type=file_type,
                link=None,
                file_size=file_size,
            )
            if active_testing:
                await uow.testings.submit_active(user_id)
            await uow.users.set_status(user_id, "submitted")
            await uow.commit()
        return submission

    async def submit_link(self, *, user_id: int, link: str) -> SubmissionRecord:
        async with self._uow_factory() as uow:
            active_testing = await uow.testings.get_active_by_user(user_id)
            submission = await uow.submissions.create(
                user_id=user_id,
                testing_id=active_testing.id if active_testing else None,
                file_id=None,
                file_type=None,
                link=link,
                file_size=None,
            )
            if active_testing:
                await uow.testings.submit_active(user_id)
            await uow.users.set_status(user_id, "submitted")
            await uow.commit()
        return submission

    async def list_pending(self) -> list[SubmissionRecord]:
        async with self._uow_factory() as uow:
            return await uow.submissions.list_pending()

    async def review(self, *, submission_id: int, reviewer_id: int, decision: str) -> ReviewOutcome:
        async with self._uow_factory() as uow:
            submission = await uow.submissions.get_by_id(submission_id)
            if submission is None:
                raise NotFoundError(f"Submission {submission_id} not found")
            await uow.submissions.review(submission_id, decision, reviewer_id)
            next_status = "awaiting_nda_front_photo" if decision == "accepted" else "rejected"
            await uow.users.set_status(submission.user_id, next_status)
            user = await uow.users.get_by_id(submission.user_id)
            await uow.commit()
        if user is None:
            raise NotFoundError(f"User {submission.user_id} not found")
        return ReviewOutcome(submission=submission, user=user, decision=decision)
