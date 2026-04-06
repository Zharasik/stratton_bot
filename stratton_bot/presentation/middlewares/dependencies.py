from __future__ import annotations

from aiogram import BaseMiddleware

from stratton_bot.container import AppContainer


class DependencyMiddleware(BaseMiddleware):
    def __init__(self, container: AppContainer) -> None:
        self._container = container

    async def __call__(self, handler, event, data):
        from_user = getattr(event, "from_user", None)
        locale = self._container.translator.resolve(getattr(from_user, "language_code", None))
        localizer = self._container.translator.for_locale(locale)
        data.update(
            {
                "container": self._container,
                "config": self._container.config,
                "localizer": localizer,
                "menu_use_case": self._container.menu_use_case,
                "testing_use_case": self._container.testing_use_case,
                "submission_use_case": self._container.submission_use_case,
                "admin_use_case": self._container.admin_use_case,
                "nda_use_case": self._container.nda_use_case,
                "task_catalog": self._container.task_catalog,
            }
        )
        return await handler(event, data)
