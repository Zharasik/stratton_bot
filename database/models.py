from sqlalchemy import Column, Integer, String, Boolean, ForeignKey, DateTime, func
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    user_id = Column(Integer, primary_key=True)
    username = Column(String, nullable=True)
    full_name = Column(String, nullable=True)
    status = Column(String, default="new")
    retry_count = Column(Integer, default=0)
    registered_at = Column(DateTime, server_default=func.now())


class TimeSlot(Base):
    __tablename__ = "time_slots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    slot_date = Column(String, nullable=False)
    slot_start = Column(String, nullable=False)
    slot_end = Column(String, nullable=False)
    booked_by = Column(Integer, ForeignKey("users.user_id"), nullable=True)
    notified = Column(Boolean, default=False)
    reminded = Column(Boolean, default=False)


class TestingRecord(Base):
    __tablename__ = "testing_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    slot_id = Column(Integer, ForeignKey("time_slots.id"), nullable=True)
    task_variant = Column(Integer, nullable=True)
    status = Column(String, default="scheduled")
    created_at = Column(DateTime, server_default=func.now())
    submitted_at = Column(DateTime, nullable=True)


class Submission(Base):
    __tablename__ = "submissions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    testing_id = Column(Integer, nullable=True)
    file_id = Column(String, nullable=True)
    file_type = Column(String, nullable=True)
    link = Column(String, nullable=True)
    file_size = Column(Integer, nullable=True)
    submitted_at = Column(DateTime, server_default=func.now())
    reviewed = Column(Boolean, default=False)
    review_result = Column(String, nullable=True)
    reviewer_id = Column(Integer, nullable=True)


class NdaRecord(Base):
    __tablename__ = "nda_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    last_name = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    middle_name = Column(String, nullable=True)
    iin = Column(String, nullable=True)
    doc_number = Column(String, nullable=True)
    birth_date = Column(String, nullable=True)
    issuing_authority = Column(String, nullable=True)
    phone = Column(String, nullable=True)
    email = Column(String, nullable=True)
    address = Column(String, nullable=True)
    nationality = Column(String, nullable=True)
    birth_place = Column(String, nullable=True)
    doc_expiry = Column(String, nullable=True)
    front_photo_id = Column(String, nullable=True)
    back_photo_id = Column(String, nullable=True)
    status = Column(String, default="pending")
    created_at = Column(DateTime, server_default=func.now())
