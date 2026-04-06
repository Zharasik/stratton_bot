from __future__ import annotations

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from stratton_bot.domain.entities import UserProfile
from stratton_bot.infrastructure.db.mappers import to_user_entity
from stratton_bot.infrastructure.db.models import UserModel


class SqlAlchemyUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(self, user_id: int, username: str | None, full_name: str | None, locale: str) -> None:
        user = await self._session.get(UserModel, user_id)
        if user is None:
            self._session.add(
                UserModel(
                    user_id=user_id,
                    username=username,
                    full_name=full_name,
                    locale=locale,
                )
            )
            return
        user.username = username
        user.full_name = full_name
        user.locale = locale

    async def get_by_id(self, user_id: int) -> UserProfile | None:
        user = await self._session.get(UserModel, user_id)
        return to_user_entity(user) if user else None

    async def set_status(self, user_id: int, status: str) -> None:
        await self._session.execute(
            update(UserModel).where(UserModel.user_id == user_id).values(status=status)
        )

    async def increment_retry(self, user_id: int) -> None:
        await self._session.execute(
            update(UserModel)
            .where(UserModel.user_id == user_id)
            .values(retry_count=UserModel.retry_count + 1)
        )

    async def list_all(self) -> list[UserProfile]:
        result = await self._session.execute(
            select(UserModel).order_by(UserModel.registered_at.desc())
        )
        return [to_user_entity(user) for user in result.scalars()]
