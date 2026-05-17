from __future__ import annotations

import logging
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from stratton_bot.application.use_cases.admin import AdminUseCase
from stratton_bot.application.use_cases.submission import SubmissionUseCase
from stratton_bot.domain.exceptions import AccessDeniedError
from stratton_bot.infrastructure.config.settings import AppConfig
from stratton_bot.infrastructure.i18n.translator import Localizer
from stratton_bot.presentation.keyboards.admin import admin_menu, admin_review
from stratton_bot.presentation.keyboards.common import main_menu
from stratton_bot.presentation.states import AdminStates

logger = logging.getLogger(__name__)
router = Router(name="admin")


def ensure_admin(user_id: int, config: AppConfig) -> None:
    AdminUseCase.ensure_admin(user_id, config.admin_ids)


@router.message(Command("admin"))
async def cmd_admin(message: Message, config: AppConfig, localizer: Localizer) -> None:
    try:
        ensure_admin(message.from_user.id, config)
    except AccessDeniedError:
        await message.answer(localizer.text("alerts.no_access"))
        return
    await message.answer(localizer.text("admin.title"), reply_markup=admin_menu(localizer))


@router.callback_query(F.data == "admin_stats")
async def cb_admin_stats(
    callback: CallbackQuery,
    admin_use_case: AdminUseCase,
    config: AppConfig,
    localizer: Localizer,
) -> None:
    try:
        ensure_admin(callback.from_user.id, config)
    except AccessDeniedError:
        await callback.answer(localizer.text("alerts.no_access"), show_alert=True)
        return
    summary = await admin_use_case.get_summary()
    await callback.message.edit_text(
        localizer.text(
            "admin.stats",
            total_users=summary.total_users,
            scheduled=summary.scheduled,
            in_progress=summary.in_progress,
            submitted=summary.submitted,
            expired=summary.expired,
            accepted=summary.accepted,
            rejected=summary.rejected,
            pending_reviews=summary.pending_reviews,
            nda_completed=summary.nda_completed,
        ),
        reply_markup=admin_menu(localizer),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_users")
async def cb_admin_users(
    callback: CallbackQuery,
    admin_use_case: AdminUseCase,
    config: AppConfig,
    localizer: Localizer,
) -> None:
    try:
        ensure_admin(callback.from_user.id, config)
    except AccessDeniedError:
        await callback.answer(localizer.text("alerts.no_access"), show_alert=True)
        return
    users = await admin_use_case.list_users()
    if not users:
        await callback.message.edit_text(localizer.text("admin.users_empty"), reply_markup=admin_menu(localizer))
        await callback.answer()
        return
    rows = []
    for index, user in enumerate(users[:20], start=1):
        rows.append(
            localizer.text(
                "admin.user_row",
                index=index,
                full_name=user.full_name or "—",
                username=f"@{user.username}" if user.username else "—",
                status=user.status,
                retry_count=user.retry_count,
            )
        )
    await callback.message.edit_text(
        localizer.text("admin.users_list", rows="\n".join(rows)),
        reply_markup=admin_menu(localizer),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_testings")
async def cb_admin_testings(
    callback: CallbackQuery,
    admin_use_case: AdminUseCase,
    config: AppConfig,
    localizer: Localizer,
) -> None:
    try:
        ensure_admin(callback.from_user.id, config)
    except AccessDeniedError:
        await callback.answer(localizer.text("alerts.no_access"), show_alert=True)
        return
    dates = await admin_use_case.list_booked_dates()
    if not dates:
        await callback.message.edit_text(localizer.text("admin.no_testings"), reply_markup=admin_menu(localizer))
        await callback.answer()
        return
    builder = InlineKeyboardBuilder()
    for item in dates:
        builder.row(
            InlineKeyboardButton(
                text=localizer.text(
                    "admin.booked_day",
                    slot_date=str(item["slot_date"]),
                    booked_count=int(item["booked_count"]),
                ),
                callback_data=f"admin_day:{item['slot_date']}",
            )
        )
    builder.row(InlineKeyboardButton(text=localizer.text("buttons.common.back"), callback_data="admin_back"))
    await callback.message.edit_text(localizer.text("admin.select_day"), reply_markup=builder.as_markup())
    await callback.answer()


@router.callback_query(F.data == "admin_back")
async def cb_admin_back(callback: CallbackQuery, localizer: Localizer) -> None:
    await callback.message.edit_text(localizer.text("admin.title"), reply_markup=admin_menu(localizer))
    await callback.answer()


@router.callback_query(F.data.startswith("admin_day:"))
async def cb_admin_day(
    callback: CallbackQuery,
    admin_use_case: AdminUseCase,
    config: AppConfig,
    localizer: Localizer,
) -> None:
    try:
        ensure_admin(callback.from_user.id, config)
    except AccessDeniedError:
        await callback.answer(localizer.text("alerts.no_access"), show_alert=True)
        return
    rows = await admin_use_case.list_booked_details(callback.data.split(":", maxsplit=1)[1])
    status_icons = {"scheduled": "📅", "in_progress": "🔄", "submitted": "📩", "expired": "⏰", "cancelled": "❌"}
    formatted_rows = [
        localizer.text(
            "admin.day_row",
            status_icon=status_icons.get(row.status or "", "❓"),
            slot_start=row.slot_start,
            slot_end=row.slot_end,
            full_name=row.full_name or "—",
            username=f" @{row.username}" if row.username else "",
            variant=f" В{row.task_variant}" if row.task_variant else "",
        )
        for row in rows
    ]
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=localizer.text("buttons.admin.testings"), callback_data="admin_testings"))
    builder.row(InlineKeyboardButton(text=localizer.text("buttons.common.back"), callback_data="admin_back"))
    await callback.message.edit_text(
        localizer.text("admin.day_details", slot_date=callback.data.split(":", maxsplit=1)[1], rows="\n".join(formatted_rows)),
        reply_markup=builder.as_markup(),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_submissions")
async def cb_admin_submissions(
    callback: CallbackQuery,
    submission_use_case: SubmissionUseCase,
    config: AppConfig,
    localizer: Localizer,
) -> None:
    try:
        ensure_admin(callback.from_user.id, config)
    except AccessDeniedError:
        await callback.answer(localizer.text("alerts.no_access"), show_alert=True)
        return
    submissions = await submission_use_case.list_pending()
    if not submissions:
        await callback.message.edit_text(localizer.text("admin.no_submissions"), reply_markup=admin_menu(localizer))
        await callback.answer()
        return
    for submission in submissions:
        text = localizer.text(
            "admin.submission_item",
            submission_id=submission.id,
            full_name=submission.full_name or submission.username or submission.user_id,
            link=f"\n🔗 {submission.link}" if submission.link else "",
        )
        try:
            markup = admin_review(localizer, submission.id)
            if submission.file_id and submission.file_type == "video":
                await callback.bot.send_video(callback.from_user.id, video=submission.file_id, caption=text, reply_markup=markup)
            elif submission.file_id:
                await callback.bot.send_document(callback.from_user.id, document=submission.file_id, caption=text, reply_markup=markup)
            else:
                await callback.bot.send_message(callback.from_user.id, text, reply_markup=markup)
        except Exception as error:
            logger.exception("Failed to send submission_id=%s to admin=%s: %s", submission.id, callback.from_user.id, error)
    await callback.answer()


@router.callback_query(F.data.startswith("review_accept:"))
async def cb_review_accept(
    callback: CallbackQuery,
    submission_use_case: SubmissionUseCase,
    config: AppConfig,
    localizer: Localizer,
    bot: Bot,
) -> None:
    try:
        ensure_admin(callback.from_user.id, config)
    except AccessDeniedError:
        await callback.answer(localizer.text("alerts.no_access"), show_alert=True)
        return
    outcome = await submission_use_case.review(
        submission_id=int(callback.data.split(":", maxsplit=1)[1]),
        reviewer_id=callback.from_user.id,
        decision="accepted",
    )
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest as error:
        logger.warning("Failed to clear review markup for message_id=%s: %s", callback.message.message_id, error)
    await callback.answer(localizer.text("admin.accepted_short"))
    await bot.send_message(outcome.user.user_id, localizer.text("messages.accepted"))
    invite_link: str | None = None
    if config.group_chat_id:
        try:
            result = await bot.create_chat_invite_link(config.group_chat_id, member_limit=1)
            invite_link = result.invite_link
        except Exception:
            logger.exception("Failed to create one-time invite link for chat_id=%s", config.group_chat_id)
            invite_link = config.group_invite_link or None
    elif config.group_invite_link:
        invite_link = config.group_invite_link
    if invite_link:
        await bot.send_message(outcome.user.user_id, localizer.text("messages.group_link", link=invite_link))
    await bot.send_message(outcome.user.user_id, localizer.text("messages.group_welcome"))
    await bot.send_message(outcome.user.user_id, localizer.text("messages.nda_intro"))
    template_path = config.static_dir / "nda_template.docx"
    if template_path.exists():
        await bot.send_document(outcome.user.user_id, document=FSInputFile(template_path, filename="NDA_Stratton.docx"))
    await bot.send_message(outcome.user.user_id, localizer.text("messages.id_photo_front"))


@router.callback_query(F.data.startswith("review_reject:"))
async def cb_review_reject(
    callback: CallbackQuery,
    submission_use_case: SubmissionUseCase,
    config: AppConfig,
    localizer: Localizer,
    bot: Bot,
) -> None:
    try:
        ensure_admin(callback.from_user.id, config)
    except AccessDeniedError:
        await callback.answer(localizer.text("alerts.no_access"), show_alert=True)
        return
    outcome = await submission_use_case.review(
        submission_id=int(callback.data.split(":", maxsplit=1)[1]),
        reviewer_id=callback.from_user.id,
        decision="rejected",
    )
    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except TelegramBadRequest as error:
        logger.warning("Failed to clear review markup for message_id=%s: %s", callback.message.message_id, error)
    await callback.answer(localizer.text("admin.rejected_short"))
    await bot.send_message(
        outcome.user.user_id,
        localizer.text("messages.rejected"),
        reply_markup=main_menu(localizer, has_testing=False),
    )


@router.callback_query(F.data == "admin_nda_search")
async def cb_admin_nda_search(callback: CallbackQuery, state: FSMContext, config: AppConfig, localizer: Localizer) -> None:
    try:
        ensure_admin(callback.from_user.id, config)
    except AccessDeniedError:
        await callback.answer(localizer.text("alerts.no_access"), show_alert=True)
        return
    await state.set_state(AdminStates.nda_search)
    await callback.message.edit_text(localizer.text("admin.nda_search_prompt"))
    await callback.answer()


@router.message(AdminStates.nda_search, Command("cancel"))
async def cancel_nda_search(message: Message, state: FSMContext, localizer: Localizer) -> None:
    await state.clear()
    await message.answer(localizer.text("admin.cancelled"), reply_markup=admin_menu(localizer))


@router.message(AdminStates.nda_search, F.text)
async def do_nda_search(message: Message, state: FSMContext, admin_use_case: AdminUseCase, localizer: Localizer) -> None:
    await state.clear()
    matches = await admin_use_case.search_nda(message.text.strip().replace("@", ""))
    if not matches:
        await message.answer(localizer.text("admin.nda_search_empty", query=message.text.strip()), reply_markup=admin_menu(localizer))
        return
    for nda, user in matches[:5]:
        await message.answer(
            localizer.text(
                "admin.nda_search_item",
                nda_id=nda.id,
                full_name=f"{nda.last_name} {nda.first_name}".strip(),
                iin=nda.iin,
                phone=nda.phone,
                email=nda.email,
                username=f"@{user.username}" if user and user.username else "—",
            )
        )
        document_path = Path("data") / f"nda_{nda.iin}.docx"
        if document_path.exists():
            await message.bot.send_document(message.from_user.id, document=FSInputFile(document_path))
        for photo_id in (nda.front_photo_id, nda.back_photo_id):
            if photo_id:
                await message.bot.send_photo(message.from_user.id, photo=photo_id)
    await message.answer(localizer.text("admin.title"), reply_markup=admin_menu(localizer))


@router.callback_query(F.data == "admin_export")
async def cb_admin_export(
    callback: CallbackQuery,
    admin_use_case: AdminUseCase,
    config: AppConfig,
    localizer: Localizer,
) -> None:
    try:
        ensure_admin(callback.from_user.id, config)
    except AccessDeniedError:
        await callback.answer(localizer.text("alerts.no_access"), show_alert=True)
        return
    exported = await admin_use_case.export_users(Path("data") / "users_export.csv")
    await callback.bot.send_document(
        callback.from_user.id,
        document=FSInputFile(exported.path, filename=exported.filename),
        caption=localizer.text("admin.export_ready"),
    )
    await callback.answer()


@router.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast(callback: CallbackQuery, state: FSMContext, config: AppConfig, localizer: Localizer) -> None:
    try:
        ensure_admin(callback.from_user.id, config)
    except AccessDeniedError:
        await callback.answer(localizer.text("alerts.no_access"), show_alert=True)
        return
    await state.set_state(AdminStates.broadcast)
    await callback.message.edit_text(localizer.text("admin.broadcast_prompt"))
    await callback.answer()


@router.message(AdminStates.broadcast, Command("cancel"))
async def cancel_broadcast(message: Message, state: FSMContext, localizer: Localizer) -> None:
    await state.clear()
    await message.answer(localizer.text("admin.cancelled"), reply_markup=admin_menu(localizer))


@router.message(AdminStates.broadcast, F.text)
async def do_broadcast(message: Message, state: FSMContext, admin_use_case: AdminUseCase, localizer: Localizer) -> None:
    await state.clear()
    users = await admin_use_case.list_users()
    success = 0
    failed = 0
    for user in users:
        try:
            await message.bot.send_message(user.user_id, message.text)
            success += 1
        except Exception as error:
            failed += 1
            logger.exception("Failed to broadcast to user_id=%s: %s", user.user_id, error)
    await message.answer(
        localizer.text("admin.broadcast_result", success=success, failed=failed),
        reply_markup=admin_menu(localizer),
    )
