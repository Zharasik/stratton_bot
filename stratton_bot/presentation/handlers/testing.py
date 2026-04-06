from __future__ import annotations

import logging
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from stratton_bot.application.use_cases.menu import MenuUseCase
from stratton_bot.application.use_cases.submission import SubmissionUseCase
from stratton_bot.application.use_cases.testing import TestingUseCase
from stratton_bot.domain.entities import ActiveTesting
from stratton_bot.domain.exceptions import ConflictError, NotFoundError, ValidationError
from stratton_bot.infrastructure.config.settings import AppConfig
from stratton_bot.infrastructure.i18n.translator import Localizer
from stratton_bot.presentation.handlers.start import format_human_date
from stratton_bot.presentation.handlers.utils import safe_edit
from stratton_bot.presentation.keyboards.admin import admin_review
from stratton_bot.presentation.keyboards.common import main_menu
from stratton_bot.presentation.keyboards.testing import (
    after_signup,
    calendar_picker,
    confirm_cancel,
    confirm_signup,
    time_slots,
)
from stratton_bot.presentation.states import SubmitStates

logger = logging.getLogger(__name__)
router = Router(name="testing")


def _testing_like(slot_date: str, slot_start: str) -> ActiveTesting:
    return ActiveTesting(
        id=0,
        user_id=0,
        slot_id=0,
        task_variant=0,
        status="scheduled",
        slot_date=slot_date,
        slot_start=slot_start,
        slot_end="",
    )


@router.callback_query(F.data == "signup_start")
async def cb_signup(
    callback: CallbackQuery,
    menu_use_case: MenuUseCase,
    config: AppConfig,
    localizer: Localizer,
) -> None:
    user, active_testing = await menu_use_case.register_user(
        user_id=callback.from_user.id,
        username=callback.from_user.username,
        full_name=callback.from_user.full_name,
        locale=localizer.locale,
    )
    if active_testing:
        await callback.answer(localizer.text("alerts.already_booked"), show_alert=True)
        return
    if user.retry_count >= config.max_retry_attempts:
        await callback.answer(localizer.text("alerts.retry_limit", limit=config.max_retry_attempts), show_alert=True)
        return
    today = datetime.now()
    await safe_edit(
        callback.message,
        localizer.text("messages.pick_date"),
        logger,
        reply_markup=calendar_picker(
            localizer,
            today.year,
            today.month,
            days_ahead=config.days_ahead,
            slot_end_hour=config.slot_end_hour,
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "cal_ignore")
async def cb_ignore(callback: CallbackQuery) -> None:
    await callback.answer()


@router.callback_query(F.data == "slot_busy")
async def cb_slot_busy(callback: CallbackQuery, localizer: Localizer) -> None:
    await callback.answer(localizer.text("alerts.slot_busy"), show_alert=True)


@router.callback_query(F.data.startswith("cal_prev:"))
async def cb_calendar_prev(callback: CallbackQuery, config: AppConfig, localizer: Localizer) -> None:
    _, year_raw, month_raw = callback.data.split(":")
    year = int(year_raw)
    month = int(month_raw) - 1
    if month < 1:
        month = 12
        year -= 1
    await callback.message.edit_reply_markup(
        reply_markup=calendar_picker(
            localizer,
            year,
            month,
            days_ahead=config.days_ahead,
            slot_end_hour=config.slot_end_hour,
        )
    )
    await callback.answer()


@router.callback_query(F.data.startswith("cal_next:"))
async def cb_calendar_next(callback: CallbackQuery, config: AppConfig, localizer: Localizer) -> None:
    _, year_raw, month_raw = callback.data.split(":")
    year = int(year_raw)
    month = int(month_raw) + 1
    if month > 12:
        month = 1
        year += 1
    await callback.message.edit_reply_markup(
        reply_markup=calendar_picker(
            localizer,
            year,
            month,
            days_ahead=config.days_ahead,
            slot_end_hour=config.slot_end_hour,
        )
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pick_date:"))
async def cb_pick_date(
    callback: CallbackQuery,
    testing_use_case: TestingUseCase,
    localizer: Localizer,
) -> None:
    date_str = callback.data.split(":", maxsplit=1)[1]
    try:
        slots = await testing_use_case.list_slots_for_date(callback.from_user.id, date_str, datetime.now())
    except ConflictError:
        await callback.answer(localizer.text("alerts.already_booked"), show_alert=True)
        return
    await safe_edit(
        callback.message,
        localizer.text("messages.pick_slot", date=format_human_date(localizer, date_str)),
        logger,
        reply_markup=time_slots(localizer, slots),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("pick_slot:"))
async def cb_pick_slot(
    callback: CallbackQuery,
    testing_use_case: TestingUseCase,
    config: AppConfig,
    localizer: Localizer,
) -> None:
    slot_id = int(callback.data.split(":", maxsplit=1)[1])
    slot = await testing_use_case.get_slot(slot_id)
    if slot is None or slot.booked_by is not None:
        await callback.answer(localizer.text("alerts.slot_busy"), show_alert=True)
        return
    deadline = testing_use_case.get_deadline(_testing_like(slot.slot_date, slot.slot_start))
    await safe_edit(
        callback.message,
        localizer.text(
            "messages.confirm_signup",
            date=format_human_date(localizer, slot.slot_date),
            slot_start=slot.slot_start,
            deadline=deadline,
            hours=config.task_hours,
        ),
        logger,
        reply_markup=confirm_signup(localizer, slot.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_slot:"))
async def cb_confirm_slot(
    callback: CallbackQuery,
    testing_use_case: TestingUseCase,
    localizer: Localizer,
) -> None:
    slot_id = int(callback.data.split(":", maxsplit=1)[1])
    try:
        testing = await testing_use_case.confirm_slot(callback.from_user.id, slot_id)
    except (ConflictError, ValidationError) as error:
        await callback.answer(str(error), show_alert=True)
        return
    await safe_edit(
        callback.message,
        localizer.text(
            "messages.signup_success",
            date=datetime.strptime(testing.slot_date, "%Y-%m-%d").strftime("%d.%m.%Y"),
            slot_start=testing.slot_start,
            deadline=testing_use_case.get_deadline(testing),
        ),
        logger,
        reply_markup=after_signup(localizer),
    )
    await callback.answer()


@router.callback_query(F.data == "remind_testing")
async def cb_remind(callback: CallbackQuery, testing_use_case: TestingUseCase, localizer: Localizer) -> None:
    testing = await testing_use_case.get_active(callback.from_user.id)
    if testing is None:
        await callback.answer(localizer.text("alerts.no_testing"), show_alert=True)
        return
    status_text = (
        localizer.text("messages.testing_active", minutes=testing_use_case.get_remaining_minutes(testing))
        if testing_use_case.is_task_available(testing)
        else localizer.text("messages.testing_pending")
    )
    await safe_edit(
        callback.message,
        localizer.text(
            "messages.testing_info",
            date=datetime.strptime(testing.slot_date, "%Y-%m-%d").strftime("%d.%m.%Y"),
            slot_start=testing.slot_start,
            deadline=testing_use_case.get_deadline(testing),
            status=status_text,
        ),
        logger,
        reply_markup=after_signup(localizer),
    )
    await callback.answer()


@router.callback_query(F.data == "cancel_testing")
async def cb_cancel(callback: CallbackQuery, localizer: Localizer) -> None:
    await safe_edit(
        callback.message,
        localizer.text("messages.cancel_confirm"),
        logger,
        reply_markup=confirm_cancel(localizer),
    )
    await callback.answer()


@router.callback_query(F.data == "confirm_cancel")
async def cb_cancel_confirm(
    callback: CallbackQuery,
    testing_use_case: TestingUseCase,
    localizer: Localizer,
) -> None:
    try:
        await testing_use_case.cancel(callback.from_user.id)
    except NotFoundError:
        await callback.answer(localizer.text("alerts.no_testing"), show_alert=True)
        return
    await safe_edit(
        callback.message,
        localizer.text("messages.cancelled"),
        logger,
        reply_markup=main_menu(localizer, has_testing=False),
    )
    await callback.answer()


@router.callback_query(F.data == "detailed_info_task")
async def cb_task_details(
    callback: CallbackQuery,
    testing_use_case: TestingUseCase,
    localizer: Localizer,
) -> None:
    testing = await testing_use_case.get_active(callback.from_user.id)
    if testing is None:
        await callback.answer(localizer.text("alerts.no_testing"), show_alert=True)
        return
    if not testing_use_case.is_task_available(testing):
        await safe_edit(
            callback.message,
            localizer.text(
                "messages.task_not_yet",
                date=datetime.strptime(testing.slot_date, "%Y-%m-%d").strftime("%d.%m.%Y"),
                slot_start=testing.slot_start,
            ),
            logger,
            reply_markup=after_signup(localizer),
        )
        await callback.answer()
        return
    await safe_edit(
        callback.message,
        localizer.text(
            "messages.task_with_deadline",
            deadline=testing_use_case.get_deadline(testing),
            task=localizer.text(f"tasks.{testing.task_variant}.full"),
        ),
        logger,
        reply_markup=after_signup(localizer),
    )
    await callback.answer()


@router.callback_query(F.data == "submit_start")
async def cb_submit_start(
    callback: CallbackQuery,
    state: FSMContext,
    testing_use_case: TestingUseCase,
    localizer: Localizer,
) -> None:
    testing = await testing_use_case.get_active(callback.from_user.id)
    if testing is None:
        await callback.answer(localizer.text("alerts.no_testing"), show_alert=True)
        return
    if not testing_use_case.is_task_available(testing):
        await callback.answer(
            localizer.text(
                "alerts.submit_window",
                slot_start=testing.slot_start,
                deadline=testing_use_case.get_deadline(testing),
            ),
            show_alert=True,
        )
        return
    await state.set_state(SubmitStates.waiting_video)
    await safe_edit(
        callback.message,
        localizer.text("messages.video_request"),
        logger,
        reply_markup=after_signup(localizer),
    )
    await callback.answer()


async def _notify_admins(
    *,
    bot: Bot,
    config: AppConfig,
    localizer: Localizer,
    submission_id: int,
    message: Message,
    file_id: str | None = None,
    link: str | None = None,
    is_document: bool = False,
) -> None:
    mention = f"@{message.from_user.username}" if message.from_user.username else message.from_user.full_name
    caption = localizer.text(
        "admin.submission_caption",
        full_name=message.from_user.full_name,
        mention=mention,
        user_id=message.from_user.id,
        link=f"\n🔗 {link}" if link else "",
    )
    for admin_id in config.admin_ids:
        try:
            markup = admin_review(localizer, submission_id)
            if file_id and is_document:
                await bot.send_document(admin_id, document=file_id, caption=caption, reply_markup=markup)
            elif file_id:
                await bot.send_video(admin_id, video=file_id, caption=caption, reply_markup=markup)
            else:
                await bot.send_message(admin_id, caption, reply_markup=markup)
        except Exception as error:
            logger.exception("Failed to notify admin_id=%s about submission_id=%s: %s", admin_id, submission_id, error)


@router.message(SubmitStates.waiting_video, F.video)
async def h_submit_video(
    message: Message,
    state: FSMContext,
    submission_use_case: SubmissionUseCase,
    config: AppConfig,
    localizer: Localizer,
    bot: Bot,
) -> None:
    if message.video.file_size and message.video.file_size > config.max_video_size_bytes:
        await message.answer(localizer.text("messages.video_too_big"))
        return
    submission = await submission_use_case.submit_file(
        user_id=message.from_user.id,
        file_id=message.video.file_id,
        file_type="video",
        file_size=message.video.file_size,
    )
    await state.clear()
    await message.answer(localizer.text("messages.video_sent"), reply_markup=main_menu(localizer, has_testing=False))
    await _notify_admins(
        bot=bot,
        config=config,
        localizer=localizer,
        submission_id=submission.id,
        message=message,
        file_id=message.video.file_id,
    )


@router.message(SubmitStates.waiting_video, F.document)
async def h_submit_document(
    message: Message,
    state: FSMContext,
    submission_use_case: SubmissionUseCase,
    config: AppConfig,
    localizer: Localizer,
    bot: Bot,
) -> None:
    document = message.document
    if not document.mime_type or not document.mime_type.startswith("video/"):
        await message.answer(localizer.text("alerts.video_or_link"))
        return
    if document.file_size and document.file_size > config.max_video_size_bytes:
        await message.answer(localizer.text("messages.video_too_big"))
        return
    submission = await submission_use_case.submit_file(
        user_id=message.from_user.id,
        file_id=document.file_id,
        file_type="document_video",
        file_size=document.file_size,
    )
    await state.clear()
    await message.answer(localizer.text("messages.video_sent"), reply_markup=main_menu(localizer, has_testing=False))
    await _notify_admins(
        bot=bot,
        config=config,
        localizer=localizer,
        submission_id=submission.id,
        message=message,
        file_id=document.file_id,
        is_document=True,
    )


@router.message(SubmitStates.waiting_video, F.text)
async def h_submit_link(
    message: Message,
    state: FSMContext,
    submission_use_case: SubmissionUseCase,
    config: AppConfig,
    localizer: Localizer,
    bot: Bot,
) -> None:
    if not (message.text.startswith("http://") or message.text.startswith("https://")):
        await message.answer(localizer.text("alerts.video_or_link"))
        return
    submission = await submission_use_case.submit_link(user_id=message.from_user.id, link=message.text.strip())
    await state.clear()
    await message.answer(localizer.text("messages.link_sent"), reply_markup=main_menu(localizer, has_testing=False))
    await _notify_admins(
        bot=bot,
        config=config,
        localizer=localizer,
        submission_id=submission.id,
        message=message,
        link=message.text.strip(),
    )


@router.message(SubmitStates.waiting_video)
async def h_submit_other(message: Message, localizer: Localizer) -> None:
    await message.answer(localizer.text("alerts.video_or_link"))
