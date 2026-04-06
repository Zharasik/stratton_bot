from __future__ import annotations

from stratton_bot.application.ports.uow import UnitOfWorkFactory
from stratton_bot.application.services.task_catalog import TaskCatalog
from stratton_bot.domain.entities import ActiveTesting, UserProgress, UserProfile
from stratton_bot.domain.exceptions import NotFoundError


class MenuUseCase:
    def __init__(self, uow_factory: UnitOfWorkFactory, task_catalog: TaskCatalog) -> None:
        self._uow_factory = uow_factory
        self._task_catalog = task_catalog

    async def register_user(
        self,
        *,
        user_id: int,
        username: str | None,
        full_name: str | None,
        locale: str,
    ) -> tuple[UserProfile, ActiveTesting | None]:
        async with self._uow_factory() as uow:
            await uow.users.upsert(user_id=user_id, username=username, full_name=full_name, locale=locale)
            user = await uow.users.get_by_id(user_id)
            active_testing = await uow.testings.get_active_by_user(user_id)
            await uow.commit()
        if user is None:
            raise NotFoundError(f"User {user_id} was not created")
        return user, active_testing

    async def get_progress(self, user_id: int) -> UserProgress:
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_id(user_id)
            active_testing = await uow.testings.get_active_by_user(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found")

        steps = {f"step{index}": "⬜" for index in range(1, 7)}
        status_map = {
            "testing_scheduled": 1,
            "in_progress": 2,
            "submitted": 3,
            "accepted": 4,
            "nda_completed": 6,
        }
        if user.status in {"awaiting_nda_front_photo", "awaiting_nda_back_photo", "nda_editing"}:
            for index in range(1, 5):
                steps[f"step{index}"] = "✅"
            steps["step5"] = "🔄"
        elif user.status == "rejected":
            for index in range(1, 4):
                steps[f"step{index}"] = "✅"
            steps["step4"] = "❌"
        elif user.status in status_map:
            for index in range(1, status_map[user.status] + 1):
                steps[f"step{index}"] = "✅"

        return UserProgress(
            user=user,
            active_testing=active_testing,
            step_marks=steps,
            variant_number=self._task_catalog.get_variant_number(user_id),
        )
