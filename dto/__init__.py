from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


@dataclass
class UserDTO:
    user_id: int
    username: Optional[str] = None
    full_name: Optional[str] = None
    status: str = "new"
    retry_count: int = 0
    registered_at: Optional[str] = None


@dataclass
class SlotDTO:
    id: int
    slot_date: str
    slot_start: str
    slot_end: str
    booked_by: Optional[int] = None
    notified: bool = False
    reminded: bool = False


@dataclass
class TestingDTO:
    id: int
    user_id: int
    slot_id: int
    task_variant: int
    status: str = "scheduled"
    slot_date: Optional[str] = None
    slot_start: Optional[str] = None
    slot_end: Optional[str] = None


@dataclass
class SubmissionDTO:
    id: int
    user_id: int
    testing_id: Optional[int] = None
    file_id: Optional[str] = None
    file_type: Optional[str] = None
    link: Optional[str] = None
    file_size: Optional[int] = None
    reviewed: bool = False
    review_result: Optional[str] = None
    username: Optional[str] = None
    full_name: Optional[str] = None


@dataclass
class NdaDTO:
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
    front_photo_id: Optional[str] = None
    back_photo_id: Optional[str] = None
    status: str = "pending"
    created_at: Optional[str] = None


@dataclass
class StatsDTO:
    total_users: int = 0
    scheduled: int = 0
    in_progress: int = 0
    submitted: int = 0
    expired: int = 0
    accepted: int = 0
    rejected: int = 0
    pending_reviews: int = 0
    nda_completed: int = 0


@dataclass
class BookedSlotDetailDTO:
    slot_date: str
    slot_start: str
    slot_end: str
    full_name: Optional[str] = None
    username: Optional[str] = None
    user_id: Optional[int] = None
    status: Optional[str] = None
    task_variant: Optional[int] = None
