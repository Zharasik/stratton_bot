from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class UserProfile:
    user_id: int
    username: str | None = None
    full_name: str | None = None
    status: str = "new"
    retry_count: int = 0
    locale: str = "ru"
    registered_at: datetime | None = None


@dataclass(slots=True)
class TimeSlot:
    id: int
    slot_date: str
    slot_start: str
    slot_end: str
    booked_by: int | None = None
    notified: bool = False
    reminded: bool = False


@dataclass(slots=True)
class ActiveTesting:
    id: int
    user_id: int
    slot_id: int
    task_variant: int
    status: str
    slot_date: str
    slot_start: str
    slot_end: str
    created_at: datetime | None = None
    submitted_at: datetime | None = None


@dataclass(slots=True)
class SubmissionRecord:
    id: int
    user_id: int
    testing_id: int | None = None
    file_id: str | None = None
    file_type: str | None = None
    link: str | None = None
    file_size: int | None = None
    reviewed: bool = False
    review_result: str | None = None
    reviewer_id: int | None = None
    username: str | None = None
    full_name: str | None = None
    submitted_at: datetime | None = None


@dataclass(slots=True)
class NdaRecordData:
    id: int
    user_id: int
    last_name: str = ""
    first_name: str = ""
    middle_name: str = ""
    iin: str = ""
    doc_number: str = ""
    birth_date: str = ""
    issuing_authority: str = ""
    phone: str = ""
    email: str = ""
    address: str = ""
    nationality: str = ""
    birth_place: str = ""
    doc_expiry: str = ""
    front_photo_id: str | None = None
    back_photo_id: str | None = None
    status: str = "pending"
    created_at: datetime | None = None


@dataclass(slots=True)
class StatsSummary:
    total_users: int = 0
    scheduled: int = 0
    in_progress: int = 0
    submitted: int = 0
    expired: int = 0
    accepted: int = 0
    rejected: int = 0
    pending_reviews: int = 0
    nda_completed: int = 0


@dataclass(slots=True)
class BookedSlotDetail:
    slot_date: str
    slot_start: str
    slot_end: str
    full_name: str | None = None
    username: str | None = None
    user_id: int | None = None
    status: str | None = None
    task_variant: int | None = None


@dataclass(slots=True)
class ReminderTarget:
    slot_id: int
    user_id: int


@dataclass(slots=True)
class NotificationTarget:
    slot_id: int
    user_id: int
    testing_id: int


@dataclass(slots=True)
class IdentityCardFront:
    last_name: str = ""
    first_name: str = ""
    middle_name: str = ""
    iin: str = ""
    doc_number: str = ""
    birth_date: str = ""


@dataclass(slots=True)
class IdentityCardBack:
    issuing_authority: str = ""
    nationality: str = ""
    birth_place: str = ""
    doc_expiry: str = ""
    doc_number: str = ""


@dataclass(slots=True)
class ExportedFile:
    path: Path
    filename: str


@dataclass(slots=True)
class UserProgress:
    user: UserProfile
    active_testing: ActiveTesting | None
    step_marks: dict[str, str]
    variant_number: int


@dataclass(slots=True)
class ReviewOutcome:
    submission: SubmissionRecord
    user: UserProfile
    decision: str


@dataclass(slots=True)
class OCRExtraction:
    side: str
    payload: dict[str, Any] = field(default_factory=dict)
