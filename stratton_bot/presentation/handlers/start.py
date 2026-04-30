from __future__ import annotations

import hashlib
import hmac
import logging
from datetime import datetime

from aiogram import F, Router
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery, Message

from stratton_bot.application.use_cases.menu import MenuUseCase
from stratton_bot.application.use_cases.nda import NDAUseCase
from stratton_bot.infrastructure.config.settings import AppConfig
from stratton_bot.infrastructure.i18n.translator import Localizer
from stratton_bot.presentation.handlers.utils import safe_edit
from stratton_bot.presentation.keyboards.common import back_to_main, faq_menu, main_menu

logger = logging.getLogger(__name__)
router = Router(name="start")

_NDA_STATUSES = {"awaiting_nda_front_photo", "awaiting_nda_back_photo", "nda_editing", "nda_completed"}


def _nda_form_url(web_app_url: str, secret: str, nda_id: int, user_id: int) -> str:
    token = hmac.new(secret.encode(), f"{nda_id}:{user_id}".encode(), hashlib.sha256).hexdigest()
    return f"{web_app_url}/form/{nda_id}?token={token}"


async def _get_nda_url(user_id: int, user_status: str, nda_use_case: NDAUseCase, config: AppConfig) -> str:
    if not config.web_app_url or user_status not in _NDA_STATUSES:
        return ""
    try:
        draft = await nda_use_case.get_or_create_draft(user_id)
        return _nda_form_url(config.web_app_url, config.webapp_secret_key, draft.id, user_id)
    except Exception:
        return ""


@router.message(CommandStart())
async def cmd_start(
    message: Message,
    menu_use_case: MenuUseCase,
    nda_use_case: NDAUseCase,
    config: AppConfig,
    localizer: Localizer,
) -> None:
    user = message.from_user
    mention = f"@{user.username}" if user and user.username else (user.full_name if user else "user")
    registered_user, active_testing = await menu_use_case.register_user(
        user_id=user.id,
        username=user.username,
        full_name=user.full_name,
        locale=localizer.locale,
    )
    nda_url = await _get_nda_url(user.id, registered_user.status, nda_use_case, config)
    await message.answer(
        localizer.text("messages.welcome", mention=mention),
        reply_markup=main_menu(localizer, has_testing=bool(active_testing), nda_url=nda_url),
    )


@router.callback_query(F.data == "main_menu")
async def cb_main(
    callback: CallbackQuery,
    menu_use_case: MenuUseCase,
    nda_use_case: NDAUseCase,
    config: AppConfig,
    localizer: Localizer,
) -> None:
    registered_user, active_testing = await menu_use_case.register_user(
        user_id=callback.from_user.id,
        username=callback.from_user.username,
        full_name=callback.from_user.full_name,
        locale=localizer.locale,
    )
    nda_url = await _get_nda_url(callback.from_user.id, registered_user.status, nda_use_case, config)
    await safe_edit(
        callback.message,
        localizer.text("messages.main_menu"),
        logger,
        reply_markup=main_menu(localizer, has_testing=bool(active_testing), nda_url=nda_url),
    )
    await callback.answer()


@router.callback_query(F.data == "about_company")
async def cb_about(callback: CallbackQuery, localizer: Localizer) -> None:
    await safe_edit(
        callback.message,
        localizer.text("messages.company_info"),
        logger,
        reply_markup=back_to_main(localizer),
    )
    await callback.answer()


@router.callback_query(F.data == "contacts")
async def cb_contacts(callback: CallbackQuery, localizer: Localizer) -> None:
    await safe_edit(
        callback.message,
        localizer.text("messages.contacts"),
        logger,
        reply_markup=back_to_main(localizer),
    )
    await callback.answer()


@router.callback_query(F.data == "my_progress")
async def cb_progress(callback: CallbackQuery, menu_use_case: MenuUseCase, localizer: Localizer) -> None:
    progress = await menu_use_case.get_progress(callback.from_user.id)
    active_slot = ""
    if progress.active_testing:
        active_slot = localizer.text(
            "messages.progress_slot",
            slot_date=progress.active_testing.slot_date,
            slot_start=progress.active_testing.slot_start,
        )
    await safe_edit(
        callback.message,
        localizer.text(
            "messages.progress",
            step1=progress.step_marks["step1"],
            step2=progress.step_marks["step2"],
            step3=progress.step_marks["step3"],
            step4=progress.step_marks["step4"],
            step5=progress.step_marks["step5"],
            step6=progress.step_marks["step6"],
            variant=progress.variant_number,
            retry=progress.user.retry_count,
            active_slot=active_slot,
        ),
        logger,
        reply_markup=back_to_main(localizer),
    )
    await callback.answer()


@router.callback_query(F.data == "faq")
async def cb_faq(callback: CallbackQuery, localizer: Localizer) -> None:
    await safe_edit(
        callback.message,
        localizer.text("messages.faq_title"),
        logger,
        reply_markup=faq_menu(localizer),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("faq:"))
async def cb_faq_item(callback: CallbackQuery, localizer: Localizer) -> None:
    topic = callback.data.split(":", maxsplit=1)[1]
    answer = localizer.mapping("faq.answers").get(topic, localizer.text("messages.not_found"))
    await safe_edit(
        callback.message,
        localizer.text("messages.faq_item", answer=answer),
        logger,
        reply_markup=faq_menu(localizer),
    )
    await callback.answer()


def format_human_date(localizer: Localizer, date_str: str) -> str:
    current = datetime.strptime(date_str, "%Y-%m-%d")
    month_name = localizer.mapping("calendar.months_genitive")[str(current.month)]
    return f"{current.day} {month_name} {current.year}"
