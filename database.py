import aiosqlite
import logging
import os
import shutil
from datetime import datetime, timedelta
from typing import Optional
from zoneinfo import ZoneInfo
from config import TIMEZONE, BACKUP_DIR

logger = logging.getLogger(__name__)
TZ = ZoneInfo(TIMEZONE)


def now_local() -> datetime:
    return datetime.now(TZ)


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self.db: Optional[aiosqlite.Connection] = None

    async def connect(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self.db = await aiosqlite.connect(self.db_path)
        self.db.row_factory = aiosqlite.Row
        await self._create_tables()
        logger.info("БД подключена: %s", self.db_path)

    async def close(self):
        if self.db:
            await self.db.close()

    def backup(self):
        os.makedirs(BACKUP_DIR, exist_ok=True)
        ts = now_local().strftime("%Y%m%d_%H%M%S")
        dst = os.path.join(BACKUP_DIR, f"backup_{ts}.db")
        shutil.copy2(self.db_path, dst)
        old = sorted(os.listdir(BACKUP_DIR))
        while len(old) > 7:
            os.remove(os.path.join(BACKUP_DIR, old.pop(0)))
        logger.info("Backup: %s", dst)

    async def _create_tables(self):
        await self.db.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                registered_at TEXT DEFAULT (datetime('now')),
                is_admin INTEGER DEFAULT 0,
                status TEXT DEFAULT 'new',
                retry_count INTEGER DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS time_slots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                slot_date TEXT NOT NULL,
                slot_start TEXT NOT NULL,
                slot_end TEXT NOT NULL,
                booked_by INTEGER,
                notified INTEGER DEFAULT 0,
                reminded INTEGER DEFAULT 0,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(slot_date, slot_start),
                FOREIGN KEY (booked_by) REFERENCES users(user_id)
            );
            CREATE TABLE IF NOT EXISTS testing_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                slot_id INTEGER,
                task_variant INTEGER,
                status TEXT DEFAULT 'scheduled',
                created_at TEXT DEFAULT (datetime('now')),
                submitted_at TEXT,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (slot_id) REFERENCES time_slots(id)
            );
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                testing_id INTEGER,
                file_id TEXT,
                file_type TEXT,
                link TEXT,
                file_size INTEGER,
                submitted_at TEXT DEFAULT (datetime('now')),
                reviewed INTEGER DEFAULT 0,
                review_result TEXT,
                reviewer_id INTEGER,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
            CREATE TABLE IF NOT EXISTS nda_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                last_name TEXT, first_name TEXT, middle_name TEXT,
                iin TEXT, doc_number TEXT, birth_date TEXT,
                issuing_authority TEXT, phone TEXT, email TEXT,
                address TEXT, nationality TEXT, birth_place TEXT,
                doc_expiry TEXT, front_photo_id TEXT, back_photo_id TEXT,
                status TEXT DEFAULT 'pending',
                created_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            );
        """)
        await self.db.commit()

    async def add_user(self, user_id: int, username: str = None, full_name: str = None):
        await self.db.execute(
            "INSERT INTO users (user_id, username, full_name) VALUES (?, ?, ?) ON CONFLICT(user_id) DO UPDATE SET username=?, full_name=?",
            (user_id, username, full_name, username, full_name))
        await self.db.commit()

    async def get_user(self, user_id: int) -> Optional[dict]:
        c = await self.db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        r = await c.fetchone()
        return dict(r) if r else None

    async def set_user_status(self, user_id: int, status: str):
        await self.db.execute("UPDATE users SET status = ? WHERE user_id = ?", (status, user_id))
        await self.db.commit()

    async def get_all_users(self) -> list:
        c = await self.db.execute("SELECT * FROM users ORDER BY registered_at DESC")
        return [dict(r) for r in await c.fetchall()]

    async def get_retry_count(self, user_id: int) -> int:
        c = await self.db.execute("SELECT retry_count FROM users WHERE user_id = ?", (user_id,))
        r = await c.fetchone()
        return r["retry_count"] if r else 0

    async def increment_retry(self, user_id: int):
        await self.db.execute("UPDATE users SET retry_count = retry_count + 1 WHERE user_id = ?", (user_id,))
        await self.db.commit()

    async def ensure_slots(self, date_str: str, start_hour: int, end_hour: int):
        c = await self.db.execute("SELECT COUNT(*) as cnt FROM time_slots WHERE slot_date = ?", (date_str,))
        r = await c.fetchone()
        if r["cnt"] > 0:
            return
        for h in range(start_hour, end_hour):
            await self.db.execute(
                "INSERT OR IGNORE INTO time_slots (slot_date, slot_start, slot_end) VALUES (?, ?, ?)",
                (date_str, f"{h:02d}:00", f"{(h+1):02d}:00"))
        await self.db.commit()

    async def get_all_slots(self, date_str: str) -> list:
        c = await self.db.execute("SELECT * FROM time_slots WHERE slot_date = ? ORDER BY slot_start", (date_str,))
        return [dict(r) for r in await c.fetchall()]

    async def get_slot(self, slot_id: int) -> Optional[dict]:
        c = await self.db.execute("SELECT * FROM time_slots WHERE id = ?", (slot_id,))
        r = await c.fetchone()
        return dict(r) if r else None

    async def book_slot(self, slot_id: int, user_id: int) -> bool:
        s = await self.get_slot(slot_id)
        if not s or s["booked_by"] is not None:
            return False
        slot_start_dt = datetime.strptime(f"{s['slot_date']} {s['slot_start']}", "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
        if slot_start_dt <= now_local():
            return False
        await self.db.execute("UPDATE time_slots SET booked_by = ? WHERE id = ? AND booked_by IS NULL", (user_id, slot_id))
        await self.db.commit()
        u = await self.get_slot(slot_id)
        return u and u["booked_by"] == user_id

    async def free_slot(self, slot_id: int):
        await self.db.execute("UPDATE time_slots SET booked_by = NULL, notified = 0, reminded = 0 WHERE id = ?", (slot_id,))
        await self.db.commit()

    async def get_booked_dates(self) -> list:
        c = await self.db.execute("SELECT slot_date, COUNT(*) as booked_count FROM time_slots WHERE booked_by IS NOT NULL GROUP BY slot_date ORDER BY slot_date")
        return [dict(r) for r in await c.fetchall()]

    async def get_booked_slots_detailed(self) -> list:
        c = await self.db.execute(
            """SELECT ts.slot_date, ts.slot_start, ts.slot_end, u.full_name, u.username, u.user_id, tr.status, tr.task_variant
               FROM time_slots ts
               JOIN users u ON ts.booked_by = u.user_id
               LEFT JOIN testing_records tr ON tr.slot_id = ts.id AND tr.user_id = u.user_id
               WHERE ts.booked_by IS NOT NULL
               ORDER BY ts.slot_date, ts.slot_start""")
        return [dict(r) for r in await c.fetchall()]

    async def get_booked_slots_by_date(self, date_str: str) -> list:
        c = await self.db.execute(
            """SELECT ts.slot_date, ts.slot_start, ts.slot_end, u.full_name, u.username, u.user_id, tr.status, tr.task_variant
               FROM time_slots ts
               JOIN users u ON ts.booked_by = u.user_id
               LEFT JOIN testing_records tr ON tr.slot_id = ts.id AND tr.user_id = u.user_id
               WHERE ts.booked_by IS NOT NULL AND ts.slot_date = ?
               ORDER BY ts.slot_start""", (date_str,))
        return [dict(r) for r in await c.fetchall()]

    async def get_slots_to_remind(self, date_str: str, hour_str: str) -> list:
        c = await self.db.execute(
            """SELECT ts.*, tr.user_id as uid FROM time_slots ts
               JOIN testing_records tr ON tr.slot_id = ts.id
               WHERE ts.slot_date = ? AND ts.slot_start = ? AND ts.booked_by IS NOT NULL
               AND ts.reminded = 0 AND tr.status = 'scheduled'""",
            (date_str, hour_str))
        return [dict(r) for r in await c.fetchall()]

    async def mark_reminded(self, slot_id: int):
        await self.db.execute("UPDATE time_slots SET reminded = 1 WHERE id = ?", (slot_id,))
        await self.db.commit()

    async def get_slots_to_notify(self, date_str: str, hour_str: str) -> list:
        c = await self.db.execute(
            """SELECT ts.*, tr.user_id as uid, tr.id as tr_id FROM time_slots ts
               JOIN testing_records tr ON tr.slot_id = ts.id
               WHERE ts.slot_date = ? AND ts.slot_start = ? AND ts.booked_by IS NOT NULL
               AND ts.notified = 0 AND tr.status = 'scheduled'""",
            (date_str, hour_str))
        return [dict(r) for r in await c.fetchall()]

    async def mark_notified(self, slot_id: int):
        await self.db.execute("UPDATE time_slots SET notified = 1 WHERE id = ?", (slot_id,))
        await self.db.commit()

    async def expire_old_slots(self, task_hours: int):
        n = now_local()
        c = await self.db.execute(
            """SELECT tr.id as tr_id, tr.slot_id, tr.user_id, ts.slot_date, ts.slot_start
               FROM testing_records tr JOIN time_slots ts ON tr.slot_id = ts.id
               WHERE tr.status IN ('scheduled', 'in_progress')""")
        rows = await c.fetchall()
        expired = []
        for r in rows:
            r = dict(r)
            start = datetime.strptime(f"{r['slot_date']} {r['slot_start']}", "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
            deadline = start + timedelta(hours=task_hours)
            if n > deadline:
                await self.db.execute("UPDATE testing_records SET status = 'expired' WHERE id = ?", (r["tr_id"],))
                await self.free_slot(r["slot_id"])
                expired.append(r["user_id"])
        if expired:
            await self.db.commit()
        return expired

    async def create_testing(self, user_id: int, slot_id: int, task_variant: int) -> int:
        c = await self.db.execute(
            "INSERT INTO testing_records (user_id, slot_id, task_variant) VALUES (?, ?, ?)",
            (user_id, slot_id, task_variant))
        await self.db.commit()
        return c.lastrowid

    async def get_active_testing(self, user_id: int) -> Optional[dict]:
        c = await self.db.execute(
            """SELECT t.*, s.slot_date, s.slot_start, s.slot_end FROM testing_records t
               JOIN time_slots s ON t.slot_id = s.id
               WHERE t.user_id = ? AND t.status IN ('scheduled', 'in_progress')
               ORDER BY t.created_at DESC LIMIT 1""", (user_id,))
        r = await c.fetchone()
        return dict(r) if r else None

    async def cancel_testing(self, user_id: int):
        t = await self.get_active_testing(user_id)
        if t:
            await self.db.execute("UPDATE testing_records SET status = 'cancelled' WHERE id = ?", (t["id"],))
            await self.free_slot(t["slot_id"])
            await self.db.commit()

    async def submit_testing(self, user_id: int):
        await self.db.execute(
            "UPDATE testing_records SET status = 'submitted', submitted_at = datetime('now') WHERE user_id = ? AND status IN ('scheduled', 'in_progress')",
            (user_id,))
        await self.db.commit()

    async def add_submission(self, **kwargs):
        cols = ", ".join(kwargs.keys())
        phs = ", ".join(["?"] * len(kwargs))
        await self.db.execute(f"INSERT INTO submissions ({cols}) VALUES ({phs})", tuple(kwargs.values()))
        await self.db.commit()

    async def get_pending_submissions(self) -> list:
        c = await self.db.execute(
            "SELECT s.*, u.username, u.full_name FROM submissions s JOIN users u ON s.user_id = u.user_id WHERE s.reviewed = 0 ORDER BY s.submitted_at DESC")
        return [dict(r) for r in await c.fetchall()]

    async def get_submission(self, sub_id: int) -> Optional[dict]:
        c = await self.db.execute("SELECT * FROM submissions WHERE id = ?", (sub_id,))
        r = await c.fetchone()
        return dict(r) if r else None

    async def review_submission(self, sub_id: int, result: str, reviewer_id: int):
        await self.db.execute("UPDATE submissions SET reviewed = 1, review_result = ?, reviewer_id = ? WHERE id = ?", (result, reviewer_id, sub_id))
        await self.db.commit()

    async def create_nda(self, user_id: int) -> int:
        c = await self.db.execute("INSERT INTO nda_records (user_id) VALUES (?)", (user_id,))
        await self.db.commit()
        return c.lastrowid

    async def update_nda(self, nda_id: int, **kwargs):
        s = ", ".join(f"{k} = ?" for k in kwargs)
        await self.db.execute(f"UPDATE nda_records SET {s} WHERE id = ?", (*kwargs.values(), nda_id))
        await self.db.commit()

    async def get_nda(self, user_id: int) -> Optional[dict]:
        c = await self.db.execute("SELECT * FROM nda_records WHERE user_id = ? ORDER BY created_at DESC LIMIT 1", (user_id,))
        r = await c.fetchone()
        return dict(r) if r else None

    async def get_all_ndas(self) -> list:
        c = await self.db.execute("SELECT * FROM nda_records WHERE status = 'completed' ORDER BY created_at DESC")
        return [dict(r) for r in await c.fetchall()]

    async def get_user_detail(self, user_id: int) -> dict:
        u = await self.get_user(user_id)
        t = await self.get_active_testing(user_id)
        n = await self.get_nda(user_id)
        c = await self.db.execute("SELECT COUNT(*) as cnt FROM submissions WHERE user_id = ?", (user_id,))
        sc = (await c.fetchone())["cnt"]
        return {"user": u, "testing": t, "nda": n, "submissions_count": sc}

    async def get_stats_summary(self) -> dict:
        async def cnt(q):
            c = await self.db.execute(q)
            return (await c.fetchone())[0]
        return {
            "total_users": await cnt("SELECT COUNT(*) FROM users"),
            "scheduled": await cnt("SELECT COUNT(*) FROM testing_records WHERE status='scheduled'"),
            "in_progress": await cnt("SELECT COUNT(*) FROM testing_records WHERE status='in_progress'"),
            "submitted": await cnt("SELECT COUNT(*) FROM testing_records WHERE status='submitted'"),
            "expired": await cnt("SELECT COUNT(*) FROM testing_records WHERE status='expired'"),
            "accepted": await cnt("SELECT COUNT(*) FROM submissions WHERE review_result='accepted'"),
            "rejected": await cnt("SELECT COUNT(*) FROM submissions WHERE review_result='rejected'"),
            "pending_reviews": await cnt("SELECT COUNT(*) FROM submissions WHERE reviewed=0"),
            "nda_completed": await cnt("SELECT COUNT(*) FROM nda_records WHERE status='completed'"),
        }

    async def export_users_csv(self, path: str):
        users = await self.get_all_users()
        import csv
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["ID", "Username", "ФИО", "Статус", "Попытки", "Дата регистрации"])
            for u in users:
                w.writerow([u["user_id"], u.get("username", ""), u.get("full_name", ""), u["status"], u.get("retry_count", 0), u["registered_at"]])