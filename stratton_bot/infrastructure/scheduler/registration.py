from __future__ import annotations

from aiogram import Bot
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from stratton_bot.container import AppContainer
from stratton_bot.infrastructure.scheduler.jobs import backup_job, expire_job, notify_job, remind_job


def register_scheduler(scheduler: AsyncIOScheduler, container: AppContainer, bot: Bot) -> None:
    scheduler.add_job(remind_job, "interval", seconds=30, args=[bot, container])
    scheduler.add_job(notify_job, "interval", seconds=30, args=[bot, container])
    scheduler.add_job(expire_job, "interval", minutes=5, args=[bot, container])
    scheduler.add_job(
        backup_job,
        "cron",
        hour=3,
        args=["data/stratton_bot.db", str(container.config.backup_dir)],
    )
