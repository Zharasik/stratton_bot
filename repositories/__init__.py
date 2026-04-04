import csv
import os
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo

from sqlalchemy import select, update, func, and_, delete
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User, TimeSlot, TestingRecord, Submission, NdaRecord
from database.session import DatabaseManager
from dto import (
    UserDTO, SlotDTO, TestingDTO, SubmissionDTO,
    NdaDTO, StatsDTO, BookedSlotDetailDTO,
)


class UserRepository:
    def __init__(self, db: DatabaseManager):
        self._db = db

    async def upsert(self, user_id: int, username: str = None, full_name: str = None):
        async with self._db.session() as s:
            existing = await s.get(User, user_id)
            if existing:
                existing.username = username
                existing.full_name = full_name
            else:
                s.add(User(user_id=user_id, username=username, full_name=full_name))

    async def get(self, user_id: int) -> Optional[UserDTO]:
        async with self._db.session() as s:
            u = await s.get(User, user_id)
            if not u:
                return None
            return UserDTO(
                user_id=u.user_id, username=u.username, full_name=u.full_name,
                status=u.status, retry_count=u.retry_count,
                registered_at=str(u.registered_at) if u.registered_at else None,
            )

    async def set_status(self, user_id: int, status: str):
        async with self._db.session() as s:
            await s.execute(update(User).where(User.user_id == user_id).values(status=status))

    async def increment_retry(self, user_id: int):
        async with self._db.session() as s:
            await s.execute(
                update(User).where(User.user_id == user_id).values(retry_count=User.retry_count + 1)
            )

    async def get_all(self) -> list[UserDTO]:
        async with self._db.session() as s:
            result = await s.execute(select(User).order_by(User.registered_at.desc()))
            return [
                UserDTO(
                    user_id=u.user_id, username=u.username, full_name=u.full_name,
                    status=u.status, retry_count=u.retry_count,
                    registered_at=str(u.registered_at) if u.registered_at else None,
                )
                for u in result.scalars()
            ]

    async def export_csv(self, path: str):
        users = await self.get_all()
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["ID", "Username", "ФИО", "Статус", "Попытки", "Дата"])
            for u in users:
                w.writerow([u.user_id, u.username or "", u.full_name or "", u.status, u.retry_count, u.registered_at or ""])


class SlotRepository:
    def __init__(self, db: DatabaseManager):
        self._db = db

    async def ensure_slots(self, date_str: str, start_hour: int, end_hour: int):
        async with self._db.session() as s:
            result = await s.execute(
                select(func.count()).where(TimeSlot.slot_date == date_str)
            )
            if result.scalar() > 0:
                return
            for h in range(start_hour, end_hour):
                s.add(TimeSlot(slot_date=date_str, slot_start=f"{h:02d}:00", slot_end=f"{h + 1:02d}:00"))

    async def get_all_for_date(self, date_str: str) -> list[SlotDTO]:
        async with self._db.session() as s:
            result = await s.execute(
                select(TimeSlot).where(TimeSlot.slot_date == date_str).order_by(TimeSlot.slot_start)
            )
            return [
                SlotDTO(id=t.id, slot_date=t.slot_date, slot_start=t.slot_start,
                        slot_end=t.slot_end, booked_by=t.booked_by)
                for t in result.scalars()
            ]

    async def get_by_id(self, slot_id: int) -> Optional[SlotDTO]:
        async with self._db.session() as s:
            t = await s.get(TimeSlot, slot_id)
            if not t:
                return None
            return SlotDTO(id=t.id, slot_date=t.slot_date, slot_start=t.slot_start,
                           slot_end=t.slot_end, booked_by=t.booked_by)

    async def book(self, slot_id: int, user_id: int) -> bool:
        async with self._db.session() as s:
            t = await s.get(TimeSlot, slot_id)
            if not t or t.booked_by is not None:
                return False
            t.booked_by = user_id
            return True

    async def free(self, slot_id: int):
        async with self._db.session() as s:
            t = await s.get(TimeSlot, slot_id)
            if t:
                t.booked_by = None
                t.notified = False
                t.reminded = False

    async def get_booked_dates(self) -> list[dict]:
        async with self._db.session() as s:
            result = await s.execute(
                select(TimeSlot.slot_date, func.count().label("cnt"))
                .where(TimeSlot.booked_by.isnot(None))
                .group_by(TimeSlot.slot_date)
                .order_by(TimeSlot.slot_date)
            )
            return [{"slot_date": r[0], "booked_count": r[1]} for r in result]

    async def get_booked_details_by_date(self, date_str: str) -> list[BookedSlotDetailDTO]:
        async with self._db.session() as s:
            result = await s.execute(
                select(TimeSlot, User, TestingRecord)
                .join(User, TimeSlot.booked_by == User.user_id)
                .outerjoin(TestingRecord, and_(
                    TestingRecord.slot_id == TimeSlot.id,
                    TestingRecord.user_id == User.user_id
                ))
                .where(and_(TimeSlot.slot_date == date_str, TimeSlot.booked_by.isnot(None)))
                .order_by(TimeSlot.slot_start)
            )
            return [
                BookedSlotDetailDTO(
                    slot_date=ts.slot_date, slot_start=ts.slot_start, slot_end=ts.slot_end,
                    full_name=u.full_name, username=u.username, user_id=u.user_id,
                    status=tr.status if tr else None, task_variant=tr.task_variant if tr else None,
                )
                for ts, u, tr in result
            ]

    async def get_slots_to_remind(self, date_str: str, hour_str: str) -> list[dict]:
        async with self._db.session() as s:
            result = await s.execute(
                select(TimeSlot, TestingRecord)
                .join(TestingRecord, TimeSlot.id == TestingRecord.slot_id)
                .where(and_(
                    TimeSlot.slot_date == date_str,
                    TimeSlot.slot_start == hour_str,
                    TimeSlot.booked_by.isnot(None),
                    TimeSlot.reminded == False,
                    TestingRecord.status == "scheduled",
                ))
            )
            return [{"slot_id": ts.id, "user_id": tr.user_id} for ts, tr in result]

    async def mark_reminded(self, slot_id: int):
        async with self._db.session() as s:
            await s.execute(update(TimeSlot).where(TimeSlot.id == slot_id).values(reminded=True))

    async def get_slots_to_notify(self, date_str: str, hour_str: str) -> list[dict]:
        async with self._db.session() as s:
            result = await s.execute(
                select(TimeSlot, TestingRecord)
                .join(TestingRecord, TimeSlot.id == TestingRecord.slot_id)
                .where(and_(
                    TimeSlot.slot_date == date_str,
                    TimeSlot.slot_start == hour_str,
                    TimeSlot.booked_by.isnot(None),
                    TimeSlot.notified == False,
                    TestingRecord.status == "scheduled",
                ))
            )
            return [{"slot_id": ts.id, "user_id": tr.user_id, "tr_id": tr.id} for ts, tr in result]

    async def mark_notified(self, slot_id: int):
        async with self._db.session() as s:
            await s.execute(update(TimeSlot).where(TimeSlot.id == slot_id).values(notified=True))


class TestingRepository:
    def __init__(self, db: DatabaseManager):
        self._db = db

    async def create(self, user_id: int, slot_id: int, task_variant: int) -> int:
        async with self._db.session() as s:
            rec = TestingRecord(user_id=user_id, slot_id=slot_id, task_variant=task_variant)
            s.add(rec)
            await s.flush()
            return rec.id

    async def get_active(self, user_id: int) -> Optional[TestingDTO]:
        async with self._db.session() as s:
            result = await s.execute(
                select(TestingRecord, TimeSlot)
                .join(TimeSlot, TestingRecord.slot_id == TimeSlot.id)
                .where(and_(
                    TestingRecord.user_id == user_id,
                    TestingRecord.status.in_(["scheduled", "in_progress"]),
                ))
                .order_by(TestingRecord.created_at.desc())
                .limit(1)
            )
            row = result.first()
            if not row:
                return None
            tr, ts = row
            return TestingDTO(
                id=tr.id, user_id=tr.user_id, slot_id=tr.slot_id,
                task_variant=tr.task_variant, status=tr.status,
                slot_date=ts.slot_date, slot_start=ts.slot_start, slot_end=ts.slot_end,
            )

    async def cancel(self, user_id: int, slot_repo: SlotRepository):
        testing = await self.get_active(user_id)
        if not testing:
            return
        async with self._db.session() as s:
            await s.execute(
                update(TestingRecord).where(TestingRecord.id == testing.id).values(status="cancelled")
            )
        await slot_repo.free(testing.slot_id)

    async def submit(self, user_id: int):
        async with self._db.session() as s:
            await s.execute(
                update(TestingRecord)
                .where(and_(
                    TestingRecord.user_id == user_id,
                    TestingRecord.status.in_(["scheduled", "in_progress"]),
                ))
                .values(status="submitted", submitted_at=func.now())
            )

    async def set_in_progress(self, tr_id: int):
        async with self._db.session() as s:
            await s.execute(
                update(TestingRecord).where(TestingRecord.id == tr_id).values(status="in_progress")
            )

    async def expire_old(self, task_hours: int, tz: ZoneInfo, slot_repo: SlotRepository) -> list[int]:
        now = datetime.now(tz)
        async with self._db.session() as s:
            result = await s.execute(
                select(TestingRecord, TimeSlot)
                .join(TimeSlot, TestingRecord.slot_id == TimeSlot.id)
                .where(TestingRecord.status.in_(["scheduled", "in_progress"]))
            )
            expired_users = []
            for tr, ts in result:
                start = datetime.strptime(f"{ts.slot_date} {ts.slot_start}", "%Y-%m-%d %H:%M").replace(tzinfo=tz)
                if now > start + timedelta(hours=task_hours):
                    tr.status = "expired"
                    expired_users.append(tr.user_id)
            await s.commit()

        for uid in expired_users:
            testing = await self.get_active(uid)
            if testing:
                await slot_repo.free(testing.slot_id)
        return expired_users


class SubmissionRepository:
    def __init__(self, db: DatabaseManager):
        self._db = db

    async def create(self, user_id: int, testing_id: int = None, file_id: str = None,
                     file_type: str = None, link: str = None, file_size: int = None):
        async with self._db.session() as s:
            s.add(Submission(
                user_id=user_id, testing_id=testing_id, file_id=file_id,
                file_type=file_type, link=link, file_size=file_size,
            ))

    async def get_pending(self) -> list[SubmissionDTO]:
        async with self._db.session() as s:
            result = await s.execute(
                select(Submission, User)
                .join(User, Submission.user_id == User.user_id)
                .where(Submission.reviewed == False)
                .order_by(Submission.submitted_at.desc())
            )
            return [
                SubmissionDTO(
                    id=sub.id, user_id=sub.user_id, testing_id=sub.testing_id,
                    file_id=sub.file_id, file_type=sub.file_type, link=sub.link,
                    file_size=sub.file_size, reviewed=sub.reviewed,
                    username=u.username, full_name=u.full_name,
                )
                for sub, u in result
            ]

    async def get_by_id(self, sub_id: int) -> Optional[SubmissionDTO]:
        async with self._db.session() as s:
            sub = await s.get(Submission, sub_id)
            if not sub:
                return None
            return SubmissionDTO(
                id=sub.id, user_id=sub.user_id, testing_id=sub.testing_id,
                file_id=sub.file_id, file_type=sub.file_type, link=sub.link,
            )

    async def review(self, sub_id: int, result: str, reviewer_id: int):
        async with self._db.session() as s:
            await s.execute(
                update(Submission)
                .where(Submission.id == sub_id)
                .values(reviewed=True, review_result=result, reviewer_id=reviewer_id)
            )


class NdaRepository:
    def __init__(self, db: DatabaseManager):
        self._db = db

    async def create(self, user_id: int) -> int:
        async with self._db.session() as s:
            rec = NdaRecord(user_id=user_id)
            s.add(rec)
            await s.flush()
            return rec.id

    async def update_fields(self, nda_id: int, **kwargs):
        async with self._db.session() as s:
            await s.execute(update(NdaRecord).where(NdaRecord.id == nda_id).values(**kwargs))

    async def get_all_completed(self) -> list[NdaDTO]:
        async with self._db.session() as s:
            result = await s.execute(
                select(NdaRecord).where(NdaRecord.status == "completed").order_by(NdaRecord.created_at.desc())
            )
            return [self._to_dto(n) for n in result.scalars()]

    async def search(self, query: str, user_repo: UserRepository) -> list[tuple[NdaDTO, Optional[UserDTO]]]:
        ndas = await self.get_all_completed()
        found = []
        for n in ndas:
            searchable = f"{n.last_name} {n.first_name} {n.middle_name} {n.iin}".lower()
            user = await user_repo.get(n.user_id)
            if user:
                searchable += f" {user.username or ''} {user.full_name or ''}".lower()
            if query.lower() in searchable:
                found.append((n, user))
        return found

    @staticmethod
    def _to_dto(n: NdaRecord) -> NdaDTO:
        return NdaDTO(
            id=n.id, user_id=n.user_id, last_name=n.last_name or "", first_name=n.first_name or "",
            middle_name=n.middle_name or "", iin=n.iin or "", doc_number=n.doc_number or "",
            birth_date=n.birth_date or "", issuing_authority=n.issuing_authority or "",
            phone=n.phone or "", email=n.email or "", address=n.address or "",
            nationality=n.nationality or "", birth_place=n.birth_place or "",
            doc_expiry=n.doc_expiry or "", front_photo_id=n.front_photo_id,
            back_photo_id=n.back_photo_id, status=n.status,
            created_at=str(n.created_at) if n.created_at else None,
        )


class StatsRepository:
    def __init__(self, db: DatabaseManager):
        self._db = db

    async def get_summary(self) -> StatsDTO:
        async with self._db.session() as s:
            async def cnt(model, *filters):
                q = select(func.count()).select_from(model)
                for f in filters:
                    q = q.where(f)
                return (await s.execute(q)).scalar() or 0

            return StatsDTO(
                total_users=await cnt(User),
                scheduled=await cnt(TestingRecord, TestingRecord.status == "scheduled"),
                in_progress=await cnt(TestingRecord, TestingRecord.status == "in_progress"),
                submitted=await cnt(TestingRecord, TestingRecord.status == "submitted"),
                expired=await cnt(TestingRecord, TestingRecord.status == "expired"),
                accepted=await cnt(Submission, Submission.review_result == "accepted"),
                rejected=await cnt(Submission, Submission.review_result == "rejected"),
                pending_reviews=await cnt(Submission, Submission.reviewed == False),
                nda_completed=await cnt(NdaRecord, NdaRecord.status == "completed"),
            )
