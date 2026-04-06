from __future__ import annotations

from stratton_bot.domain.entities import (
    ActiveTesting,
    BookedSlotDetail,
    NdaRecordData,
    SubmissionRecord,
    TimeSlot,
    UserProfile,
)
from stratton_bot.infrastructure.db.models import (
    NdaRecordModel,
    SubmissionModel,
    TestingRecordModel,
    TimeSlotModel,
    UserModel,
)


def to_user_entity(model: UserModel) -> UserProfile:
    return UserProfile(
        user_id=model.user_id,
        username=model.username,
        full_name=model.full_name,
        status=model.status,
        retry_count=model.retry_count,
        locale=model.locale,
        registered_at=model.registered_at,
    )


def to_slot_entity(model: TimeSlotModel) -> TimeSlot:
    return TimeSlot(
        id=model.id,
        slot_date=model.slot_date,
        slot_start=model.slot_start,
        slot_end=model.slot_end,
        booked_by=model.booked_by,
        notified=model.notified,
        reminded=model.reminded,
    )


def to_testing_entity(model: TestingRecordModel, slot: TimeSlotModel) -> ActiveTesting:
    return ActiveTesting(
        id=model.id,
        user_id=model.user_id,
        slot_id=model.slot_id or 0,
        task_variant=model.task_variant or 0,
        status=model.status,
        slot_date=slot.slot_date,
        slot_start=slot.slot_start,
        slot_end=slot.slot_end,
        created_at=model.created_at,
        submitted_at=model.submitted_at,
    )


def to_submission_entity(model: SubmissionModel, user: UserModel | None = None) -> SubmissionRecord:
    return SubmissionRecord(
        id=model.id,
        user_id=model.user_id,
        testing_id=model.testing_id,
        file_id=model.file_id,
        file_type=model.file_type,
        link=model.link,
        file_size=model.file_size,
        reviewed=model.reviewed,
        review_result=model.review_result,
        reviewer_id=model.reviewer_id,
        username=user.username if user else None,
        full_name=user.full_name if user else None,
        submitted_at=model.submitted_at,
    )


def to_nda_entity(model: NdaRecordModel) -> NdaRecordData:
    return NdaRecordData(
        id=model.id,
        user_id=model.user_id,
        last_name=model.last_name or "",
        first_name=model.first_name or "",
        middle_name=model.middle_name or "",
        iin=model.iin or "",
        doc_number=model.doc_number or "",
        birth_date=model.birth_date or "",
        issuing_authority=model.issuing_authority or "",
        phone=model.phone or "",
        email=model.email or "",
        address=model.address or "",
        nationality=model.nationality or "",
        birth_place=model.birth_place or "",
        doc_expiry=model.doc_expiry or "",
        front_photo_id=model.front_photo_id,
        back_photo_id=model.back_photo_id,
        status=model.status,
        created_at=model.created_at,
    )


def to_booked_detail(slot: TimeSlotModel, user: UserModel, testing: TestingRecordModel | None) -> BookedSlotDetail:
    return BookedSlotDetail(
        slot_date=slot.slot_date,
        slot_start=slot.slot_start,
        slot_end=slot.slot_end,
        full_name=user.full_name,
        username=user.username,
        user_id=user.user_id,
        status=testing.status if testing else None,
        task_variant=testing.task_variant if testing else None,
    )
