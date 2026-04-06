from __future__ import annotations

from aiogram import Dispatcher

from stratton_bot.container import AppContainer
from stratton_bot.presentation.middlewares.dependencies import DependencyMiddleware


def register_middlewares(dispatcher: Dispatcher, container: AppContainer) -> None:
    dispatcher.update.outer_middleware(DependencyMiddleware(container))
