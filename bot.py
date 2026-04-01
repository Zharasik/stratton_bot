import asyncio
import logging
import sys
from datetime import timedelta
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from config import BOT_TOKEN, ADMIN_IDS, TASK_HOURS, REMIND_BEFORE_MINUTES, get_task_for_user, get_task_variant_number
from database import Database, now_local

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[logging.StreamHandler(sys.stdout), logging.FileHandler("data/bot.log", encoding="utf-8")]
)
logger = logging.getLogger(__name__)


class DatabaseMiddleware:
    def __init__(self, db: Database):
        self.db = db
    async def __call__(self, handler, event, data):
        data["db"] = self.db
        return await handler(event, data)


async def scheduler(bot: Bot, db: Database):
    last_backup_date = None
    while True:
        try:
            n = now_local()
            date_str = n.strftime("%Y-%m-%d")
            current_hour = f"{n.hour:02d}:00"

            remind_time = n + timedelta(minutes=REMIND_BEFORE_MINUTES)
            remind_hour = f"{remind_time.hour:02d}:00"
            if remind_time.date() == n.date():
                rows = await db.get_slots_to_remind(date_str, remind_hour)
                for r in rows:
                    try:
                        await bot.send_message(r["uid"],
                            f"⏰ <b>Напоминание!</b>\n\nВаше тестирование начнётся через {REMIND_BEFORE_MINUTES} минут ({r['slot_start']}).\nПодготовьтесь!",
                            parse_mode="HTML")
                        await db.mark_reminded(r["id"])
                        logger.info("Remind sent to %s", r["uid"])
                    except Exception as e:
                        logger.error("Remind error %s: %s", r["uid"], e)

            rows = await db.get_slots_to_notify(date_str, current_hour)
            for r in rows:
                try:
                    uid = r["uid"]
                    task = get_task_for_user(uid)
                    deadline_dt = n.replace(minute=0, second=0) + timedelta(hours=TASK_HOURS)
                    deadline = deadline_dt.strftime("%H:%M")
                    await bot.send_message(uid,
                        f"🔔 <b>Тестирование началось!</b>\n\n🕐 Начало: {r['slot_start']}\n⏱ Дедлайн: {deadline} (3 часа)\n\nЗадание ниже 👇",
                        parse_mode="HTML")
                    await bot.send_message(uid, task, parse_mode="HTML")
                    await db.db.execute("UPDATE testing_records SET status = 'in_progress' WHERE id = ?", (r["tr_id"],))
                    await db.db.commit()
                    await db.mark_notified(r["id"])
                    for admin_id in ADMIN_IDS:
                        try:
                            user = await db.get_user(uid)
                            name = user["full_name"] if user else str(uid)
                            await bot.send_message(admin_id, f"📋 Кандидат <b>{name}</b> начал тестирование (вариант {get_task_variant_number(uid)})", parse_mode="HTML")
                        except Exception:
                            pass
                    logger.info("Start notification sent to %s", uid)
                except Exception as e:
                    logger.error("Notify error %s: %s", r.get("uid"), e)

            expired = await db.expire_old_slots(TASK_HOURS)
            for uid in expired:
                try:
                    await bot.send_message(uid, "⏰ <b>Время вышло!</b>\n\nВаш слот истёк. Вы можете записаться снова.", parse_mode="HTML")
                    logger.info("Expired notification sent to %s", uid)
                except Exception:
                    pass

            today = n.date()
            if last_backup_date != today and n.hour >= 3:
                try:
                    db.backup()
                    last_backup_date = today
                except Exception as e:
                    logger.error("Backup error: %s", e)

        except Exception as e:
            logger.error("Scheduler error: %s", e)
        await asyncio.sleep(30)


async def main():
    logger.info("Запуск Stratton Internship Bot")
    logger.info("ADMIN_IDS: %s", ADMIN_IDS)
    if BOT_TOKEN == "YOUR_BOT_TOKEN_HERE":
        logger.error("Установите BOT_TOKEN в .env!")
        sys.exit(1)
    db = Database("data/stratton_bot.db")
    await db.connect()
    session = AiohttpSession(timeout=300)
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML), session=session)
    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(DatabaseMiddleware(db))
    dp.callback_query.middleware(DatabaseMiddleware(db))
    from handlers import admin_router, test_router, start_router, testing_router, nda_router, nda_catch_router
    dp.include_router(admin_router)
    dp.include_router(test_router)
    dp.include_router(start_router)
    dp.include_router(testing_router)
    dp.include_router(nda_router)
    dp.include_router(nda_catch_router)
    task = asyncio.create_task(scheduler(bot, db))
    logger.info("Бот запущен!")
    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        task.cancel()
        await db.close()
        await bot.session.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Ctrl+C")
