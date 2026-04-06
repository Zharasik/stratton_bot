from __future__ import annotations

import logging

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message


async def safe_edit(message: Message, text: str, logger: logging.Logger, **kwargs) -> None:
    try:
        await message.edit_text(text, **kwargs)
    except TelegramBadRequest as error:
        logger.warning(
            "Failed to edit message_id=%s chat_id=%s: %s",
            message.message_id,
            message.chat.id,
            error,
        )
