from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class UserModel(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    full_name: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="new")
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    locale: Mapped[str] = mapped_column(String, default="ru")
    registered_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class TimeSlotModel(Base):
    __tablename__ = "time_slots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slot_date: Mapped[str] = mapped_column(String, nullable=False)
    slot_start: Mapped[str] = mapped_column(String, nullable=False)
    slot_end: Mapped[str] = mapped_column(String, nullable=False)
    booked_by: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"), nullable=True)
    notified: Mapped[bool] = mapped_column(Boolean, default=False)
    reminded: Mapped[bool] = mapped_column(Boolean, default=False)


class TestingRecordModel(Base):
    __tablename__ = "testing_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    slot_id: Mapped[int | None] = mapped_column(ForeignKey("time_slots.id"), nullable=True)
    task_variant: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String, default="scheduled")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SubmissionModel(Base):
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    testing_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    file_id: Mapped[str | None] = mapped_column(String, nullable=True)
    file_type: Mapped[str | None] = mapped_column(String, nullable=True)
    link: Mapped[str | None] = mapped_column(String, nullable=True)
    file_size: Mapped[int | None] = mapped_column(Integer, nullable=True)
    submitted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    review_result: Mapped[str | None] = mapped_column(String, nullable=True)
    reviewer_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class NdaRecordModel(Base):
    __tablename__ = "nda_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    last_name: Mapped[str | None] = mapped_column(String, nullable=True)
    first_name: Mapped[str | None] = mapped_column(String, nullable=True)
    middle_name: Mapped[str | None] = mapped_column(String, nullable=True)
    iin: Mapped[str | None] = mapped_column(String, nullable=True)
    doc_number: Mapped[str | None] = mapped_column(String, nullable=True)
    birth_date: Mapped[str | None] = mapped_column(String, nullable=True)
    issuing_authority: Mapped[str | None] = mapped_column(String, nullable=True)
    phone: Mapped[str | None] = mapped_column(String, nullable=True)
    email: Mapped[str | None] = mapped_column(String, nullable=True)
    address: Mapped[str | None] = mapped_column(String, nullable=True)
    nationality: Mapped[str | None] = mapped_column(String, nullable=True)
    birth_place: Mapped[str | None] = mapped_column(String, nullable=True)
    doc_expiry: Mapped[str | None] = mapped_column(String, nullable=True)
    front_photo_id: Mapped[str | None] = mapped_column(String, nullable=True)
    back_photo_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, default="pending")
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
