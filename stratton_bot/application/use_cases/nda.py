from __future__ import annotations

from pathlib import Path

from stratton_bot.application.ports.uow import NDADocumentGenerator, UnitOfWorkFactory
from stratton_bot.application.use_cases.ocr import IdentityCardOCRUseCase
from stratton_bot.domain.entities import NdaRecordData, OCRExtraction
from stratton_bot.domain.exceptions import ConflictError, NotFoundError, ValidationError


class NDAUseCase:
    REQUIRED_FIELDS = ("last_name", "first_name", "iin", "phone", "email", "address")

    def __init__(
        self,
        uow_factory: UnitOfWorkFactory,
        ocr_use_case: IdentityCardOCRUseCase,
        document_generator: NDADocumentGenerator,
        data_dir: Path,
    ) -> None:
        self._uow_factory = uow_factory
        self._ocr_use_case = ocr_use_case
        self._document_generator = document_generator
        self._data_dir = data_dir

    async def get_user_status(self, user_id: int) -> str:
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_id(user_id)
        if user is None:
            raise NotFoundError(f"User {user_id} not found")
        return user.status

    async def get_or_create_draft(self, user_id: int) -> NdaRecordData:
        async with self._uow_factory() as uow:
            draft = await uow.ndas.get_pending_by_user(user_id)
            if draft is None:
                draft = await uow.ndas.create(user_id)
                await uow.commit()
        return draft

    async def process_photo(
        self, *, user_id: int, image_bytes: bytes
    ) -> tuple[OCRExtraction, int]:
        """Run OCR, persist extracted fields to DB draft, return (extraction, nda_id)."""
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_id(user_id)
            if user is None:
                raise NotFoundError(f"User {user_id} not found")

            if user.status == "awaiting_nda_front_photo":
                extraction = await self._ocr_use_case.recognize_front(image_bytes)
                await uow.users.set_status(user_id, "awaiting_nda_back_photo")
            elif user.status == "awaiting_nda_back_photo":
                extraction = await self._ocr_use_case.recognize_back(image_bytes)
                await uow.users.set_status(user_id, "nda_editing")
            else:
                raise ConflictError("User is not in NDA photo flow")

            # Persist extracted fields to the draft record immediately
            draft = await uow.ndas.get_pending_by_user(user_id)
            if draft is None:
                draft = await uow.ndas.create(user_id)
            fields_to_save = {k: v for k, v in extraction.payload.items() if v}
            if fields_to_save:
                await uow.ndas.update(draft.id, fields_to_save)
            await uow.commit()

        return extraction, draft.id

    async def advance_photo_step(self, user_id: int) -> str:
        async with self._uow_factory() as uow:
            user = await uow.users.get_by_id(user_id)
            if user is None:
                raise NotFoundError(f"User {user_id} not found")
            if user.status == "awaiting_nda_front_photo":
                # Still create the draft so we have an id for the webapp link
                draft = await uow.ndas.get_pending_by_user(user_id)
                if draft is None:
                    await uow.ndas.create(user_id)
                await uow.users.set_status(user_id, "awaiting_nda_back_photo")
                next_status = "awaiting_nda_back_photo"
            elif user.status == "awaiting_nda_back_photo":
                await uow.users.set_status(user_id, "nda_editing")
                next_status = "nda_editing"
            else:
                raise ConflictError("User is not in NDA photo flow")
            await uow.commit()
        return next_status

    async def complete(self, *, user_id: int, fields: dict[str, str | None]) -> tuple[NdaRecordData, Path]:
        missing = [field for field in self.REQUIRED_FIELDS if not fields.get(field)]
        if missing:
            raise ValidationError(", ".join(missing))

        async with self._uow_factory() as uow:
            # Reuse existing draft if available, otherwise create new
            nda = await uow.ndas.get_pending_by_user(user_id)
            if nda is None:
                nda = await uow.ndas.create(user_id)
            await uow.ndas.update(nda.id, {**fields, "status": "completed"})
            await uow.users.set_status(user_id, "nda_completed")
            final_nda = NdaRecordData(id=nda.id, user_id=user_id, status="completed")
            for key, value in fields.items():
                setattr(final_nda, key, value)
            output_path = self._data_dir / f"nda_{final_nda.iin or user_id}.docx"
            self._document_generator.generate(final_nda, output_path)
            await uow.commit()
        return final_nda, output_path
