from __future__ import annotations

from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from stratton_bot.infrastructure.db.models import Base


class DatabaseGateway:
    def __init__(self, database_url: str, data_dir: Path) -> None:
        data_dir.mkdir(parents=True, exist_ok=True)
        self.engine: AsyncEngine = create_async_engine(database_url, echo=False)
        self.session_factory = async_sessionmaker(
            bind=self.engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )

    async def create_tables(self) -> None:
        async with self.engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            result = await connection.execute(text("PRAGMA table_info(users)"))
            columns = {row[1] for row in result.fetchall()}
            if "locale" not in columns:
                await connection.execute(text("ALTER TABLE users ADD COLUMN locale VARCHAR DEFAULT 'ru'"))

    async def close(self) -> None:
        await self.engine.dispose()
