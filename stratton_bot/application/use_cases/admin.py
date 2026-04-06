from __future__ import annotations

from pathlib import Path

from stratton_bot.application.ports.uow import UnitOfWorkFactory, UserExporter
from stratton_bot.domain.entities import BookedSlotDetail, ExportedFile, NdaRecordData, StatsSummary, UserProfile
from stratton_bot.domain.exceptions import AccessDeniedError


class AdminUseCase:
    def __init__(self, uow_factory: UnitOfWorkFactory, exporter: UserExporter) -> None:
        self._uow_factory = uow_factory
        self._exporter = exporter

    @staticmethod
    def ensure_admin(user_id: int, admin_ids: list[int]) -> None:
        if user_id not in admin_ids:
            raise AccessDeniedError("Admin access required")

    async def get_summary(self) -> StatsSummary:
        async with self._uow_factory() as uow:
            return await uow.stats.get_summary()

    async def list_users(self) -> list[UserProfile]:
        async with self._uow_factory() as uow:
            return await uow.users.list_all()

    async def list_booked_dates(self) -> list[dict[str, int | str]]:
        async with self._uow_factory() as uow:
            return await uow.slots.list_booked_dates()

    async def list_booked_details(self, date_str: str) -> list[BookedSlotDetail]:
        async with self._uow_factory() as uow:
            return await uow.slots.list_booked_details(date_str)

    async def search_nda(self, query: str) -> list[tuple[NdaRecordData, UserProfile | None]]:
        async with self._uow_factory() as uow:
            query_normalized = query.lower()
            ndas = await uow.ndas.search(query)
            seen_ids = {nda.id for nda in ndas}
            result: list[tuple[NdaRecordData, UserProfile | None]] = []
            for nda in ndas:
                result.append((nda, await uow.users.get_by_id(nda.user_id)))
            for nda in await uow.ndas.list_completed():
                if nda.id in seen_ids:
                    continue
                user = await uow.users.get_by_id(nda.user_id)
                searchable = " ".join(
                    filter(
                        None,
                        [
                            user.username.lower() if user and user.username else "",
                            user.full_name.lower() if user and user.full_name else "",
                        ],
                    )
                )
                if query_normalized in searchable:
                    result.append((nda, user))
            return result

    async def export_users(self, output_path: Path) -> ExportedFile:
        async with self._uow_factory() as uow:
            users = await uow.users.list_all()
        exported_path = self._exporter.export(users, output_path)
        return ExportedFile(path=exported_path, filename=output_path.name)
