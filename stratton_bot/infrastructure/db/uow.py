from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from stratton_bot.infrastructure.db.repositories import (
    SqlAlchemyNDARepository,
    SqlAlchemySlotRepository,
    SqlAlchemyStatsRepository,
    SqlAlchemySubmissionRepository,
    SqlAlchemyTestingRepository,
    SqlAlchemyUserRepository,
)


class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory
        self._session: AsyncSession | None = None

    async def __aenter__(self) -> "SqlAlchemyUnitOfWork":
        self._session = self._session_factory()
        self.users = SqlAlchemyUserRepository(self._session)
        self.slots = SqlAlchemySlotRepository(self._session)
        self.testings = SqlAlchemyTestingRepository(self._session)
        self.submissions = SqlAlchemySubmissionRepository(self._session)
        self.ndas = SqlAlchemyNDARepository(self._session)
        self.stats = SqlAlchemyStatsRepository(self._session)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self._session is None:
            return
        if exc:
            await self._session.rollback()
        await self._session.close()

    async def commit(self) -> None:
        if self._session is None:
            return
        await self._session.commit()

    async def rollback(self) -> None:
        if self._session is None:
            return
        await self._session.rollback()
