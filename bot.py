import asyncio
import logging
import os
import shutil
import sys
from pathlib import Path

_root = Path(__file__).resolve().parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))
os.chdir(_root)
(_root / "data").mkdir(parents=True, exist_ok=True)

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.utils.token import TokenValidationError, validate_token
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from settings import DOTENV_PATH, get_settings
from database import DatabaseManager
from repositories import (
    UserRepository, SlotRepository, TestingRepository,
    SubmissionRepository, NdaRepository, StatsRepository,
)
from infrastructure import GeminiOCR
from services import TaskService
from handlers import build_handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("data/bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)


class DatabaseMiddleware:
    def __init__(self, repos: dict):
        self._repos = repos

    async def __call__(self, handler, event, data):
        data.update(self._repos)
        return await handler(event, data)


async def remind_job(bot: Bot, settings, slot_repo: SlotRepository):
    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz)
    remind_time = now + timedelta(minutes=settings.remind_before_minutes)
    if remind_time.date() != now.date():
        return
    date_str = now.strftime("%Y-%m-%d")
    hour_str = f"{remind_time.hour:02d}:00"
    rows = await slot_repo.get_slots_to_remind(date_str, hour_str)
    for r in rows:
        try:
            await bot.send_message(
                r["user_id"],
                f"⏰ <b>Через {settings.remind_before_minutes} мин!</b>\nПодготовьтесь!",
                parse_mode="HTML",
            )
            await slot_repo.mark_reminded(r["slot_id"])
        except Exception as e:
            logger.error("Remind error %s: %s", r["user_id"], e)


async def notify_job(bot: Bot, settings, slot_repo: SlotRepository, testing_repo: TestingRepository):
    tz = ZoneInfo(settings.timezone)
    now = datetime.now(tz)
    date_str = now.strftime("%Y-%m-%d")
    hour_str = f"{now.hour:02d}:00"
    rows = await slot_repo.get_slots_to_notify(date_str, hour_str)
    for r in rows:
        try:
            uid = r["user_id"]
            task = TaskService.get_task_text(uid)
            dl = TaskService.get_deadline(date_str, hour_str, settings.task_hours)
            await bot.send_message(uid, f"🔔 <b>Старт!</b>\n🕐 {hour_str}\n⏱ До {dl}", parse_mode="HTML")
            await bot.send_message(uid, task, parse_mode="HTML")
            await testing_repo.set_in_progress(r["tr_id"])
            await slot_repo.mark_notified(r["slot_id"])
        except Exception as e:
            logger.error("Notify error %s: %s", r.get("user_id"), e)


async def expire_job(bot: Bot, settings, testing_repo: TestingRepository, slot_repo: SlotRepository):
    tz = ZoneInfo(settings.timezone)
    expired = await testing_repo.expire_old(settings.task_hours, tz, slot_repo)
    for uid in expired:
        try:
            await bot.send_message(uid, "⏰ <b>Время вышло!</b>\nМожете записаться снова.", parse_mode="HTML")
        except Exception:
            pass


def backup_job(db_path: str, backup_dir: str):
    os.makedirs(backup_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    shutil.copy2(db_path, os.path.join(backup_dir, f"backup_{ts}.db"))
    old = sorted(os.listdir(backup_dir))
    while len(old) > 7:
        os.remove(os.path.join(backup_dir, old.pop(0)))
    logger.info("Backup done")


async def main():
    settings = get_settings()
    logger.info("Запуск Stratton Bot | ADMINS: %s", settings.admin_ids)

    _bad_tokens = ("", "YOUR_BOT_TOKEN_HERE", "......")
    if not settings.bot_token or settings.bot_token in _bad_tokens:
        env_set = bool(os.environ.get("BOT_TOKEN", "").strip())
        logger.error(
            "Нет корректного BOT_TOKEN. Ожидаемый файл: %s (существует: %s). "
            "Переменная BOT_TOKEN в окружении процесса: %s. "
            "На сервере создайте этот .env или задайте export BOT_TOKEN=... (без кавычек).",
            DOTENV_PATH,
            DOTENV_PATH.is_file(),
            "да" if env_set else "нет",
        )
        sys.exit(1)
    try:
        validate_token(settings.bot_token)
    except TokenValidationError:
        logger.error(
            "BOT_TOKEN отклонён Telegram (неверный формат или опечатка). "
            "Скопируйте токен заново из @BotFather."
        )
        sys.exit(1)

    db_manager = DatabaseManager(settings.database_url)
    await db_manager.create_tables()

    user_repo = UserRepository(db_manager)
    slot_repo = SlotRepository(db_manager)
    testing_repo = TestingRepository(db_manager)
    submission_repo = SubmissionRepository(db_manager)
    nda_repo = NdaRepository(db_manager)
    stats_repo = StatsRepository(db_manager)
    ocr = GeminiOCR(settings.gemini_api_key)

    session = AiohttpSession(timeout=300)
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML), session=session)
    dp = Dispatcher(storage=MemoryStorage())

    dp.message.middleware(DatabaseMiddleware({}))
    dp.callback_query.middleware(DatabaseMiddleware({}))

    routers = build_handlers(settings, user_repo, slot_repo, testing_repo, submission_repo, nda_repo, stats_repo, ocr)
    for r in routers:
        dp.include_router(r)

    scheduler = AsyncIOScheduler(timezone=settings.timezone)
    scheduler.add_job(remind_job, "interval", seconds=30, args=[bot, settings, slot_repo])
    scheduler.add_job(notify_job, "interval", seconds=30, args=[bot, settings, slot_repo, testing_repo])
    scheduler.add_job(expire_job, "interval", minutes=5, args=[bot, settings, testing_repo, slot_repo])
    scheduler.add_job(backup_job, "cron", hour=3, args=["data/stratton_bot.db", settings.backup_dir])
    scheduler.start()

    logger.info("Бот запущен!")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        scheduler.shutdown()
        await db_manager.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Ctrl+C")
