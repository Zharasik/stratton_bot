from __future__ import annotations

import asyncio
import hashlib
import hmac
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, InlineKeyboardButton, InlineKeyboardMarkup, Message, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from stratton_bot.application.use_cases.nda import NDAUseCase
from stratton_bot.domain.exceptions import ConflictError, NotFoundError, ValidationError
from stratton_bot.infrastructure.config.settings import AppConfig
from stratton_bot.infrastructure.i18n.translator import Localizer
from stratton_bot.presentation.constants import NDA_FIELD_KEYS, NDA_HINT_KEYS
from stratton_bot.presentation.keyboards.testing import nda_back_to_fields, nda_fields
from stratton_bot.presentation.states import NDAStates

logger = logging.getLogger(__name__)
router = Router(name="nda")


def _make_form_token(nda_id: int, user_id: int, secret: str) -> str:
    msg = f"{nda_id}:{user_id}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def _make_form_url(web_app_url: str, nda_id: int, user_id: int, secret: str) -> str:
    token = _make_form_token(nda_id, user_id, secret)
    return f"{web_app_url}/form/{nda_id}?token={token}"


def _make_form_button(label: str, form_url: str, use_webapp: bool) -> InlineKeyboardButton:
    if use_webapp:
        return InlineKeyboardButton(text=label, web_app=WebAppInfo(url=form_url))
    return InlineKeyboardButton(text=label, url=form_url)


async def _send_form_choice(
    message: Message,
    config: AppConfig,
    localizer: Localizer,
    nda_data: dict,
    nda_id: int,
    user_id: int,
    *,
    text: str | None = None,
    show_telegram_edit: bool = True,
) -> None:
    if not config.web_app_url:
        if show_telegram_edit:
            await message.answer(localizer.text("nda.fields_title"), reply_markup=nda_fields(localizer, nda_data))
        return

    form_url = _make_form_url(config.web_app_url, nda_id, user_id, config.webapp_secret_key)
    use_webapp = config.web_app_url.startswith("https://")
    builder = InlineKeyboardBuilder()
    builder.row(_make_form_button(localizer.text("buttons.nda.open_form"), form_url, use_webapp))
    if show_telegram_edit:
        builder.row(InlineKeyboardButton(
            text=localizer.text("buttons.nda.edit_in_telegram"),
            callback_data="nda_show_fields",
        ))
    await message.answer(
        text or localizer.text("nda.choose_edit_method"),
        reply_markup=builder.as_markup(),
    )


async def download_file_bytes(bot: Bot, file_id: str) -> bytes:
    for attempt in range(1, 4):
        try:
            file = await bot.get_file(file_id)
            stream = await asyncio.wait_for(bot.download_file(file.file_path), timeout=60)
            return stream.read()
        except Exception as error:
            logger.exception("Failed to download file_id=%s on attempt=%s: %s", file_id, attempt, error)
            if attempt == 3:
                raise
            await asyncio.sleep(2)
    raise RuntimeError("Unreachable")


@router.callback_query(F.data.startswith("nda_edit:"))
async def cb_nda_edit(callback: CallbackQuery, state: FSMContext, localizer: Localizer) -> None:
    field_key = callback.data.split(":", maxsplit=1)[1]
    nda_data = (await state.get_data()).get("nda_data", {})
    label_key = dict(NDA_FIELD_KEYS).get(field_key, "")
    await state.set_state(NDAStates.editing_field)
    await state.update_data(editing_field=field_key)
    await callback.message.edit_text(
        localizer.text(
            "nda.edit_field",
            label=localizer.text(label_key),
            current=nda_data.get(field_key) or localizer.text("nda.not_filled"),
            hint=localizer.text(NDA_HINT_KEYS.get(field_key, "nda.hints.default")),
        ),
        reply_markup=nda_back_to_fields(localizer),
    )
    await callback.answer()


@router.callback_query(F.data == "nda_show_fields")
async def cb_nda_show_fields(callback: CallbackQuery, state: FSMContext, localizer: Localizer) -> None:
    await state.set_state(NDAStates.editing_fields)
    nda_data = (await state.get_data()).get("nda_data", {})
    await callback.message.edit_text(localizer.text("nda.fields_title"), reply_markup=nda_fields(localizer, nda_data))
    await callback.answer()


@router.message(NDAStates.editing_field, F.text)
async def nda_field_value(message: Message, state: FSMContext, localizer: Localizer) -> None:
    data = await state.get_data()
    field_key = data.get("editing_field")
    nda_data = data.get("nda_data", {})
    value = message.text.strip()
    if field_key == "iin" and (not value.isdigit() or len(value) != 12):
        await message.answer(localizer.text("nda.validation_iin"))
        return
    if field_key == "doc_number" and not value.upper().startswith("N"):
        await message.answer(localizer.text("nda.validation_doc_number"))
        return
    nda_data[field_key] = value
    await state.update_data(nda_data=nda_data)

    found = False
    for current_key, label_key in NDA_FIELD_KEYS:
        if current_key == field_key:
            found = True
            continue
        if found and not nda_data.get(current_key):
            await state.update_data(editing_field=current_key)
            await message.answer(
                localizer.text(
                    "nda.edit_field",
                    label=localizer.text(label_key),
                    current=nda_data.get(current_key) or localizer.text("nda.not_filled"),
                    hint=localizer.text(NDA_HINT_KEYS.get(current_key, "nda.hints.default")),
                ),
                reply_markup=nda_back_to_fields(localizer),
            )
            return

    await state.set_state(NDAStates.editing_fields)
    await message.answer(localizer.text("nda.fields_title"), reply_markup=nda_fields(localizer, nda_data))


@router.callback_query(F.data == "nda_confirm")
async def cb_nda_confirm(
    callback: CallbackQuery,
    state: FSMContext,
    nda_use_case: NDAUseCase,
    config: AppConfig,
    localizer: Localizer,
    bot: Bot,
) -> None:
    nda_data = (await state.get_data()).get("nda_data", {})
    fields = {key: nda_data.get(key) for key, _ in NDA_FIELD_KEYS}
    fields["front_photo_id"] = nda_data.get("front_photo_id")
    fields["back_photo_id"] = nda_data.get("back_photo_id")
    try:
        nda_record, output_path = await nda_use_case.complete(user_id=callback.from_user.id, fields=fields)
    except ValidationError as error:
        await callback.answer(localizer.text("nda.fill_required", fields=str(error)), show_alert=True)
        return
    await state.clear()
    await callback.message.edit_text(localizer.text("nda.generated"))
    if output_path.exists():
        await bot.send_document(
            callback.from_user.id,
            document=FSInputFile(output_path, filename=f"NDA_{nda_record.last_name}.docx"),
            caption=localizer.text("nda.user_document_ready"),
        )
    admin_text = localizer.text(
        "nda.admin_created",
        nda_id=nda_record.id,
        full_name=f"{nda_record.last_name} {nda_record.first_name}",
        iin=nda_record.iin,
        phone=nda_record.phone,
        username=f"@{callback.from_user.username}" if callback.from_user.username else callback.from_user.full_name,
    )
    for admin_id in config.admin_ids:
        try:
            await bot.send_message(admin_id, admin_text)
            if output_path.exists():
                await bot.send_document(admin_id, document=FSInputFile(output_path))
            for key in ("front_photo_id", "back_photo_id"):
                if nda_data.get(key):
                    await bot.send_photo(admin_id, photo=nda_data[key])
        except Exception as error:
            logger.exception("Failed to notify admin_id=%s for nda_id=%s: %s", admin_id, nda_record.id, error)

    # Send webapp check button to user
    if config.web_app_url:
        await _send_form_choice(
            callback.message,
            config,
            localizer,
            nda_data,
            nda_record.id,
            callback.from_user.id,
            text=localizer.text("nda.check_on_web"),
        )

    await callback.answer()


@router.message(F.photo)
async def catch_nda_photo(
    message: Message,
    state: FSMContext,
    nda_use_case: NDAUseCase,
    config: AppConfig,
    localizer: Localizer,
    bot: Bot,
) -> None:
    try:
        status = await nda_use_case.get_user_status(message.from_user.id)
    except NotFoundError:
        return
    if status not in {"awaiting_nda_front_photo", "awaiting_nda_back_photo"}:
        return

    waiting_message = await message.answer(localizer.text("nda.processing"))
    nda_data = (await state.get_data()).get("nda_data", {})
    photo_id = message.photo[-1].file_id
    nda_data["front_photo_id" if status == "awaiting_nda_front_photo" else "back_photo_id"] = photo_id
    nda_id: int | None = (await state.get_data()).get("nda_id")
    try:
        image_bytes = await download_file_bytes(bot, photo_id)
        extraction, nda_id = await nda_use_case.process_photo(
            user_id=message.from_user.id, image_bytes=image_bytes
        )
        nda_data.update({key: value for key, value in extraction.payload.items() if value})
    except Exception as error:
        logger.exception("Failed to process NDA photo for user_id=%s: %s", message.from_user.id, error)
        next_status = await nda_use_case.advance_photo_step(message.from_user.id)
        # Still grab the draft id after advancing
        if nda_id is None:
            try:
                draft = await nda_use_case.get_or_create_draft(message.from_user.id)
                nda_id = draft.id
            except Exception:
                pass
        try:
            await waiting_message.edit_text(localizer.text("nda.ocr_failed"))
        except Exception as edit_error:
            logger.warning("Failed to update waiting message_id=%s: %s", waiting_message.message_id, edit_error)

    await state.update_data(nda_data=nda_data, nda_id=nda_id)

    try:
        await waiting_message.delete()
    except Exception as error:
        logger.warning("Failed to delete waiting message_id=%s: %s", waiting_message.message_id, error)

    new_status = await nda_use_case.get_user_status(message.from_user.id)
    if new_status == "awaiting_nda_back_photo":
        await message.answer(localizer.text("messages.id_photo_back"))
        return

    # Both photos processed — offer webapp form link + Telegram editing
    await state.set_state(NDAStates.editing_fields)

    if nda_id:
        await _send_form_choice(message, config, localizer, nda_data, nda_id, message.from_user.id)
    else:
        await message.answer(localizer.text("nda.fields_title"), reply_markup=nda_fields(localizer, nda_data))


_TEST_NDA_DATA = {
    "last_name": "Иванов",
    "first_name": "Иван",
    "middle_name": "Иванович",
    "iin": "123456789012",
    "doc_number": "N12345678",
    "birth_date": "01.01.1990",
    "doc_expiry": "01.01.2030",
    "issuing_authority": "МВД РК г. Алматы",
    "nationality": "Казахстан",
    "birth_place": "г. Алматы",
    "phone": "+7 777 123 45 67",
    "email": "test@example.com",
    "address": "г. Астана, ул. Тестовая, д. 1",
}


@router.message(Command("testnda"))
async def cmd_test_nda(
    message: Message,
    state: FSMContext,
    nda_use_case: NDAUseCase,
    config: AppConfig,
    localizer: Localizer,
) -> None:
    if message.from_user.id not in config.admin_ids:
        return

    nda_id = await nda_use_case.update_draft(message.from_user.id, _TEST_NDA_DATA)
    await state.update_data(nda_data=dict(_TEST_NDA_DATA), nda_id=nda_id)
    await message.answer(f"✅ Тестовая NDA запись создана (id={nda_id})")
    await _send_form_choice(message, config, localizer, dict(_TEST_NDA_DATA), nda_id, message.from_user.id)


@router.message(Command("mynda"))
async def cmd_my_nda(
    message: Message,
    nda_use_case: NDAUseCase,
    config: AppConfig,
    localizer: Localizer,
) -> None:
    try:
        draft = await nda_use_case.get_or_create_draft(message.from_user.id)
    except Exception:
        await message.answer("NDA запись не найдена.")
        return
    if not config.web_app_url:
        await message.answer("Веб-приложение не настроено. Обратитесь к администратору.")
        return
    await _send_form_choice(
        message,
        config,
        localizer,
        {},
        draft.id,
        message.from_user.id,
        text=localizer.text("nda.check_on_web"),
        show_telegram_edit=False,
    )


@router.message(F.text)
async def catch_nda_text(message: Message, state: FSMContext, nda_use_case: NDAUseCase, localizer: Localizer) -> None:
    try:
        status = await nda_use_case.get_user_status(message.from_user.id)
    except NotFoundError:
        return
    current_state = await state.get_state()
    if current_state and "NDAStates" in current_state:
        return
    if status == "awaiting_nda_front_photo":
        await message.answer(localizer.text("messages.id_photo_front"))
    elif status == "awaiting_nda_back_photo":
        await message.answer(localizer.text("messages.id_photo_back"))
