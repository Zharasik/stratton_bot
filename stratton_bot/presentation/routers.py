from __future__ import annotations

from aiogram import Dispatcher

from stratton_bot.presentation.handlers.admin import router as admin_router
from stratton_bot.presentation.handlers.nda import router as nda_router
from stratton_bot.presentation.handlers.start import router as start_router
from stratton_bot.presentation.handlers.testing import router as testing_router


def register_routers(dispatcher: Dispatcher) -> None:
    dispatcher.include_router(admin_router)
    dispatcher.include_router(start_router)
    dispatcher.include_router(testing_router)
    dispatcher.include_router(nda_router)
