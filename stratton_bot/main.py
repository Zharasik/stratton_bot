from __future__ import annotations

import asyncio
import logging
import sys
import threading
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from stratton_bot.container import AppContainer
from stratton_bot.domain.exceptions import ConfigurationError
from stratton_bot.infrastructure.config.settings import AppConfig
from stratton_bot.infrastructure.scheduler.registration import register_scheduler
from stratton_bot.presentation.middlewares.registration import register_middlewares
from stratton_bot.presentation.routers import register_routers


def configure_logging() -> None:
    Path("data").mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)-25s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("data/bot.log", encoding="utf-8"),
        ],
    )


def _start_webapp() -> None:
    try:
        import importlib.util, os
        spec = importlib.util.spec_from_file_location(
            "webapp", Path(__file__).parent.parent / "webapp" / "app.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        port = int(os.getenv("WEBAPP_PORT", "5000"))
        mod.app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False)
    except Exception as exc:
        logging.getLogger(__name__).error("Webapp failed to start: %s", exc)


async def run_async() -> None:
    configure_logging()
    logger = logging.getLogger(__name__)

    config = AppConfig.from_env()
    config.validate()

    t = threading.Thread(target=_start_webapp, daemon=True, name="webapp")
    t.start()
    logger.info("Webapp started on port %s", __import__('os').getenv('WEBAPP_PORT', '5000'))

    container = AppContainer.build(config)
    await container.db.create_tables()

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=AiohttpSession(timeout=300),
    )
    dispatcher = Dispatcher(storage=MemoryStorage())

    register_middlewares(dispatcher, container)
    register_routers(dispatcher)

    scheduler = AsyncIOScheduler(timezone=config.timezone)
    register_scheduler(scheduler=scheduler, container=container, bot=bot)
    scheduler.start()

    logger.info("Stratton bot started")
    try:
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        scheduler.shutdown(wait=False)
        await bot.session.close()
        await container.db.close()


def run() -> None:
    try:
        asyncio.run(run_async())
    except KeyboardInterrupt:
        logging.getLogger(__name__).info("Application stopped")
    except ConfigurationError as error:
        logging.getLogger(__name__).error("Configuration error: %s", error)
