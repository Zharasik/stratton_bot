from __future__ import annotations

from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from stratton_bot.domain.entities import NdaRecordData
from stratton_bot.infrastructure.db.mappers import to_nda_entity
from stratton_bot.infrastructure.db.models import NdaRecordModel


class SqlAlchemyNDARepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, user_id: int) -> NdaRecordData:
        record = NdaRecordModel(user_id=user_id)
        self._session.add(record)
        await self._session.flush()
        return to_nda_entity(record)

    async def update(self, nda_id: int, fields: dict[str, str | None]) -> None:
        record = await self._session.get(NdaRecordModel, nda_id)
        if record is None:
            return
        for key, value in fields.items():
            setattr(record, key, value)

    async def list_completed(self) -> list[NdaRecordData]:
        result = await self._session.execute(
            select(NdaRecordModel)
            .where(NdaRecordModel.status == "completed")
            .order_by(NdaRecordModel.created_at.desc())
        )
        return [to_nda_entity(record) for record in result.scalars()]

    async def search(self, query: str) -> list[NdaRecordData]:
        like = f"%{query.lower()}%"
        result = await self._session.execute(
            select(NdaRecordModel)
            .where(
                or_(
                    NdaRecordModel.iin.ilike(like),
                    NdaRecordModel.first_name.ilike(like),
                    NdaRecordModel.last_name.ilike(like),
                    NdaRecordModel.middle_name.ilike(like),
                )
            )
            .order_by(NdaRecordModel.created_at.desc())
        )
        return [to_nda_entity(record) for record in result.scalars()]
