from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from aiogram import Bot

from stratton_bot.container import AppContainer

logger = logging.getLogger(__name__)


async def remind_job(bot: Bot, container: AppContainer) -> None:
    localizer = container.translator.for_locale(container.config.default_locale)
    reminders = await container.scheduler_use_case.collect_reminders()
    for reminder in reminders:
        try:
            await bot.send_message(
                reminder.user_id,
                localizer.text(
                    "scheduler.remind",
                    minutes=container.config.remind_before_minutes,
                ),
            )
        except Exception as error:
            logger.exception("Failed to send reminder to user_id=%s: %s", reminder.user_id, error)


async def notify_job(bot: Bot, container: AppContainer) -> None:
    localizer = container.translator.for_locale(container.config.default_locale)
    notifications = await container.scheduler_use_case.collect_notifications()
    now = datetime.now(ZoneInfo(container.config.timezone))
    slot_date = now.strftime("%Y-%m-%d")
    slot_start = f"{now.hour:02d}:00"
    for notification in notifications:
        try:
            variant = container.scheduler_use_case.get_variant_number(notification.user_id)
            await bot.send_message(
                notification.user_id,
                localizer.text(
                    "scheduler.start",
                    slot_start=slot_start,
                    deadline=container.scheduler_use_case.get_deadline(slot_date, slot_start),
                ),
            )
            await bot.send_message(
                notification.user_id,
                localizer.text(f"tasks.{variant}.full"),
            )
        except Exception as error:
            logger.exception("Failed to send start task to user_id=%s: %s", notification.user_id, error)


async def expire_job(bot: Bot, container: AppContainer) -> None:
    localizer = container.translator.for_locale(container.config.default_locale)
    expired_user_ids = await container.scheduler_use_case.expire_old()
    for user_id in expired_user_ids:
        try:
            await bot.send_message(user_id, localizer.text("scheduler.expired"))
        except Exception as error:
            logger.exception("Failed to send expire notice to user_id=%s: %s", user_id, error)


def backup_job(database_path: str, backup_dir: str) -> None:
    backup_path = Path(backup_dir)
    backup_path.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = backup_path / f"backup_{timestamp}.db"
    shutil.copy2(database_path, target)
    backups = sorted(backup_path.glob("*.db"))
    while len(backups) > 7:
        oldest = backups.pop(0)
        oldest.unlink(missing_ok=True)
    logger.info("Database backup saved to %s", target)
