import logging
import os
import asyncio
from datetime import datetime

from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import InlineKeyboardButton

import texts
import keyboards
from services import TaskService, NdaDocumentService

logger = logging.getLogger(__name__)

MONTHS_RU_GENITIVE = {
    1:"января",2:"февраля",3:"марта",4:"апреля",5:"мая",6:"июня",
    7:"июля",8:"августа",9:"сентября",10:"октября",11:"ноября",12:"декабря",
}


class SubmitStates(StatesGroup):
    waiting_video = State()


class NDAStates(StatesGroup):
    editing_fields = State()
    editing_field = State()


class AdminStates(StatesGroup):
    broadcast = State()
    nda_search = State()


NDA_HINTS = {
    "last_name": "Фамилия на русском", "first_name": "Имя на русском",
    "middle_name": "Отчество", "iin": "12 цифр", "doc_number": "Начинается с N",
    "birth_date": "ДД.ММ.ГГГГ", "issuing_authority": "Оборотная сторона",
    "phone": "+7 777 123 4567", "email": "Ваш email", "address": "Адрес проживания",
    "nationality": "Оборотная сторона", "birth_place": "Оборотная сторона",
    "doc_expiry": "ДД.ММ.ГГГГ",
}


async def safe_edit(message, text, **kwargs):
    try:
        await message.edit_text(text, **kwargs)
    except Exception:
        pass


def build_handlers(settings, user_repo, slot_repo, testing_repo, submission_repo, nda_repo, stats_repo, ocr):
    start_router = Router(name="start")
    testing_router = Router(name="testing")
    nda_router = Router(name="nda")
    nda_catch_router = Router(name="nda_catch")
    admin_router = Router(name="admin")
    test_router = Router(name="test_mode")

    def is_admin(user_id: int) -> bool:
        return user_id in settings.admin_ids

    # ===================== START =====================

    @start_router.message(CommandStart())
    async def cmd_start(message: Message):
        user = message.from_user
        await user_repo.upsert(user.id, user.username, user.full_name)
        mention = f"@{user.username}" if user.username else user.full_name
        testing = await testing_repo.get_active(user.id)
        await message.answer(
            texts.WELCOME.format(mention=mention),
            reply_markup=keyboards.main_menu(has_testing=bool(testing)),
            parse_mode="HTML",
        )

    @start_router.callback_query(F.data == "main_menu")
    async def cb_main(callback: CallbackQuery):
        testing = await testing_repo.get_active(callback.from_user.id)
        await safe_edit(callback.message, texts.MAIN_MENU,
                        reply_markup=keyboards.main_menu(has_testing=bool(testing)), parse_mode="HTML")
        await callback.answer()

    @start_router.callback_query(F.data == "about_company")
    async def cb_about(callback: CallbackQuery):
        await safe_edit(callback.message, texts.COMPANY_INFO, reply_markup=keyboards.back_to_main(), parse_mode="HTML")
        await callback.answer()

    @start_router.callback_query(F.data == "contacts")
    async def cb_contacts(callback: CallbackQuery):
        await safe_edit(callback.message, texts.CONTACTS, reply_markup=keyboards.back_to_main(), parse_mode="HTML")
        await callback.answer()

    @start_router.callback_query(F.data == "my_progress")
    async def cb_progress(callback: CallbackQuery):
        uid = callback.from_user.id
        user = await user_repo.get(uid)
        if not user:
            await user_repo.upsert(uid, callback.from_user.username, callback.from_user.full_name)
            user = await user_repo.get(uid)
        status = user.status if user else "new"
        steps = {f"step{i}": "⬜" for i in range(1, 7)}
        mapping = {
            "testing_scheduled": 1, "in_progress": 2, "submitted": 3,
            "accepted": 4, "nda_completed": 6,
        }
        if status in ("awaiting_nda_front_photo", "awaiting_nda_back_photo", "nda_editing"):
            for i in range(1, 5):
                steps[f"step{i}"] = "✅"
            steps["step5"] = "🔄"
        elif status == "rejected":
            for i in range(1, 4):
                steps[f"step{i}"] = "✅"
            steps["step4"] = "❌"
        elif status in mapping:
            for i in range(1, mapping[status] + 1):
                steps[f"step{i}"] = "✅"
        variant = TaskService.get_variant_number(uid)
        retry = user.retry_count if user else 0
        extra = f"\n\n📝 Вариант: {variant}\n🔄 Попытки: {retry}"
        testing = await testing_repo.get_active(uid)
        if testing:
            extra += f"\n📅 Слот: {testing.slot_date} {testing.slot_start}"
        await safe_edit(callback.message, texts.STATUS_TRACKER.format(**steps) + extra,
                        reply_markup=keyboards.back_to_main(), parse_mode="HTML")
        await callback.answer()

    @start_router.callback_query(F.data == "faq")
    async def cb_faq(callback: CallbackQuery):
        await safe_edit(callback.message, "❓ <b>FAQ</b>\n\nВыберите тему:",
                        reply_markup=keyboards.faq_menu(), parse_mode="HTML")
        await callback.answer()

    @start_router.callback_query(F.data.startswith("faq:"))
    async def cb_faq_item(callback: CallbackQuery):
        key = callback.data.split(":")[1]
        answer = texts.FAQ.get(key, "Не найдено.")
        await safe_edit(callback.message, f"❓ <b>FAQ</b>\n\n{answer}",
                        reply_markup=keyboards.faq_menu(), parse_mode="HTML")
        await callback.answer()

    # ===================== TESTING =====================

    @testing_router.callback_query(F.data == "signup_start")
    async def cb_signup(callback: CallbackQuery):
        uid = callback.from_user.id
        existing = await testing_repo.get_active(uid)
        if existing:
            await callback.answer("Вы уже записаны!", show_alert=True)
            return
        user = await user_repo.get(uid)
        if user and user.retry_count >= settings.max_retry_attempts:
            await callback.answer(f"Лимит попыток ({settings.max_retry_attempts})!", show_alert=True)
            return
        now = datetime.now()
        await safe_edit(callback.message, "📅 <b>Выберите дату:</b>",
                        reply_markup=keyboards.calendar_picker(now.year, now.month, settings.days_ahead, settings.slot_end_hour),
                        parse_mode="HTML")
        await callback.answer()

    @testing_router.callback_query(F.data == "cal_ignore")
    async def cb_ign(callback: CallbackQuery):
        await callback.answer()

    @testing_router.callback_query(F.data == "slot_busy")
    async def cb_busy(callback: CallbackQuery):
        await callback.answer("Занято.", show_alert=True)

    @testing_router.callback_query(F.data.startswith("cal_prev:"))
    async def cb_prev(callback: CallbackQuery):
        _, y, m = callback.data.split(":")
        y, m = int(y), int(m) - 1
        if m < 1:
            m, y = 12, y - 1
        await callback.message.edit_reply_markup(
            reply_markup=keyboards.calendar_picker(y, m, settings.days_ahead, settings.slot_end_hour))
        await callback.answer()

    @testing_router.callback_query(F.data.startswith("cal_next:"))
    async def cb_next(callback: CallbackQuery):
        _, y, m = callback.data.split(":")
        y, m = int(y), int(m) + 1
        if m > 12:
            m, y = 1, y + 1
        await callback.message.edit_reply_markup(
            reply_markup=keyboards.calendar_picker(y, m, settings.days_ahead, settings.slot_end_hour))
        await callback.answer()

    @testing_router.callback_query(F.data.startswith("pick_date:"))
    async def cb_date(callback: CallbackQuery):
        date_str = callback.data.split(":")[1]
        await slot_repo.ensure_slots(date_str, settings.slot_start_hour, settings.slot_end_hour)
        slots = await slot_repo.get_all_for_date(date_str)
        now = datetime.now()
        if date_str == now.strftime("%Y-%m-%d"):
            slots = [s for s in slots if int(s.slot_start.split(":")[0]) >= now.hour + 1]
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        nice = f"{dt.day} {MONTHS_RU_GENITIVE[dt.month]} {dt.year}"
        await safe_edit(callback.message, f"🕐 <b>{nice}</b>\n\nВыберите час ({settings.task_hours}ч на задание):",
                        reply_markup=keyboards.time_slots(slots), parse_mode="HTML")
        await callback.answer()

    @testing_router.callback_query(F.data.startswith("pick_slot:"))
    async def cb_slot(callback: CallbackQuery):
        slot = await slot_repo.get_by_id(int(callback.data.split(":")[1]))
        if not slot or slot.booked_by:
            await callback.answer("Занято!", show_alert=True)
            return
        dt = datetime.strptime(slot.slot_date, "%Y-%m-%d")
        nice = f"{dt.day} {MONTHS_RU_GENITIVE[dt.month]} {dt.year}"
        dl = TaskService.get_deadline(slot.slot_date, slot.slot_start, settings.task_hours)
        await safe_edit(callback.message,
            f"📋 <b>Подтверждение:</b>\n\n📅 {nice}\n🕐 {slot.slot_start}\n⏱ До {dl}\n\nПодтверждаете?",
            reply_markup=keyboards.confirm_signup(slot.id), parse_mode="HTML")
        await callback.answer()

    @testing_router.callback_query(F.data.startswith("confirm_slot:"))
    async def cb_confirm(callback: CallbackQuery):
        slot_id = int(callback.data.split(":")[1])
        uid = callback.from_user.id
        if not await slot_repo.book(slot_id, uid):
            await callback.answer("Занято!", show_alert=True)
            return
        variant = TaskService.get_variant_number(uid)
        await testing_repo.create(uid, slot_id, variant)
        await user_repo.set_status(uid, "testing_scheduled")
        await user_repo.increment_retry(uid)
        slot = await slot_repo.get_by_id(slot_id)
        dt = datetime.strptime(slot.slot_date, "%Y-%m-%d")
        dl = TaskService.get_deadline(slot.slot_date, slot.slot_start, settings.task_hours)
        await safe_edit(callback.message,
            texts.SIGNUP_SUCCESS.format(date=dt.strftime("%d.%m.%Y"), time_start=slot.slot_start, time_end=dl),
            reply_markup=keyboards.after_signup(), parse_mode="HTML")
        await callback.answer()

    @testing_router.callback_query(F.data == "remind_testing")
    async def cb_remind(callback: CallbackQuery):
        t = await testing_repo.get_active(callback.from_user.id)
        if not t:
            await callback.answer("Нет записей!", show_alert=True)
            return
        dl = TaskService.get_deadline(t.slot_date, t.slot_start, settings.task_hours)
        active = TaskService.is_within_window(t.slot_date, t.slot_start, settings.task_hours)
        if active:
            mins = TaskService.get_remaining_minutes(t.slot_date, t.slot_start, settings.task_hours)
            st = f"🟢 Активно! Осталось {mins} мин"
        else:
            st = "⏳ Ожидание"
        dt = datetime.strptime(t.slot_date, "%Y-%m-%d")
        await safe_edit(callback.message,
            f"📅 <b>Запись:</b>\n\n📅 {dt.strftime('%d.%m.%Y')}\n🕐 {t.slot_start}\n⏱ До {dl}\n📌 {st}",
            reply_markup=keyboards.after_signup(), parse_mode="HTML")
        await callback.answer()

    @testing_router.callback_query(F.data == "cancel_testing")
    async def cb_cancel(callback: CallbackQuery):
        await safe_edit(callback.message, "⚠️ Отменить?", reply_markup=keyboards.confirm_cancel(), parse_mode="HTML")
        await callback.answer()

    @testing_router.callback_query(F.data == "confirm_cancel")
    async def cb_do_cancel(callback: CallbackQuery):
        await testing_repo.cancel(callback.from_user.id, slot_repo)
        await user_repo.set_status(callback.from_user.id, "cancelled")
        await safe_edit(callback.message, "❌ Отменено.",
                        reply_markup=keyboards.main_menu(has_testing=False), parse_mode="HTML")
        await callback.answer()

    @testing_router.callback_query(F.data == "detailed_info_task")
    async def cb_detail(callback: CallbackQuery):
        t = await testing_repo.get_active(callback.from_user.id)
        if not t:
            await callback.answer("Нет тестирования!", show_alert=True)
            return
        if not TaskService.is_within_window(t.slot_date, t.slot_start, settings.task_hours):
            dt = datetime.strptime(t.slot_date, "%Y-%m-%d")
            await safe_edit(callback.message,
                texts.TASK_NOT_YET.format(date=dt.strftime("%d.%m.%Y"), time_start=t.slot_start),
                reply_markup=keyboards.after_signup(), parse_mode="HTML")
            await callback.answer()
            return
        dl = TaskService.get_deadline(t.slot_date, t.slot_start, settings.task_hours)
        task = TaskService.get_task_text(callback.from_user.id)
        await safe_edit(callback.message, f"⏰ <b>Дедлайн: {dl}</b>\n\n{task}",
                        reply_markup=keyboards.back_to_main(), parse_mode="HTML")
        await callback.answer()

    @testing_router.callback_query(F.data == "submit_start")
    async def cb_submit(callback: CallbackQuery, state: FSMContext):
        t = await testing_repo.get_active(callback.from_user.id)
        if not t:
            await callback.answer("Нет тестирования!", show_alert=True)
            return
        if not TaskService.is_within_window(t.slot_date, t.slot_start, settings.task_hours):
            dl = TaskService.get_deadline(t.slot_date, t.slot_start, settings.task_hours)
            await callback.answer(f"Доступно с {t.slot_start} до {dl}", show_alert=True)
            return
        await state.set_state(SubmitStates.waiting_video)
        await safe_edit(callback.message, texts.VIDEO_REQUEST,
                        reply_markup=keyboards.back_to_main(), parse_mode="HTML")
        await callback.answer()

    async def _notify_admins(bot: Bot, user, file_id=None, link=None, is_doc=False):
        un = f"@{user.username}" if user.username else user.full_name
        variant = TaskService.get_variant_number(user.id)
        cap = f"📩 <b>Работа!</b>\n👤 {user.full_name} ({un})\n📝 В{variant}\n🆔 <code>{user.id}</code>"
        if link:
            cap += f"\n🔗 {link}"
        subs = await submission_repo.get_pending()
        sub_id = subs[0].id if subs else 0
        for aid in settings.admin_ids:
            try:
                if file_id and is_doc:
                    await bot.send_document(aid, document=file_id, caption=cap,
                                            reply_markup=keyboards.admin_review(sub_id), parse_mode="HTML")
                elif file_id:
                    await bot.send_video(aid, video=file_id, caption=cap,
                                         reply_markup=keyboards.admin_review(sub_id), parse_mode="HTML")
                else:
                    await bot.send_message(aid, cap, reply_markup=keyboards.admin_review(sub_id), parse_mode="HTML")
            except Exception as e:
                logger.error("Admin notify error: %s", e)

    @testing_router.message(SubmitStates.waiting_video, F.video)
    async def h_video(message: Message, state: FSMContext, bot: Bot):
        if message.video.file_size and message.video.file_size > settings.max_video_size_bytes:
            await message.answer(texts.VIDEO_TOO_BIG)
            return
        t = await testing_repo.get_active(message.from_user.id)
        await submission_repo.create(
            user_id=message.from_user.id, testing_id=t.id if t else None,
            file_id=message.video.file_id, file_type="video", file_size=message.video.file_size)
        if t:
            await testing_repo.submit(message.from_user.id)
        await user_repo.set_status(message.from_user.id, "submitted")
        await state.clear()
        await message.answer(texts.VIDEO_SENT, reply_markup=keyboards.main_menu(has_testing=False), parse_mode="HTML")
        await _notify_admins(bot, message.from_user, file_id=message.video.file_id)

    @testing_router.message(SubmitStates.waiting_video, F.document)
    async def h_doc(message: Message, state: FSMContext, bot: Bot):
        doc = message.document
        if doc.mime_type and doc.mime_type.startswith("video/"):
            if doc.file_size and doc.file_size > settings.max_video_size_bytes:
                await message.answer(texts.VIDEO_TOO_BIG)
                return
            t = await testing_repo.get_active(message.from_user.id)
            await submission_repo.create(
                user_id=message.from_user.id, testing_id=t.id if t else None,
                file_id=doc.file_id, file_type="document_video", file_size=doc.file_size)
            if t:
                await testing_repo.submit(message.from_user.id)
            await user_repo.set_status(message.from_user.id, "submitted")
            await state.clear()
            await message.answer(texts.VIDEO_SENT, reply_markup=keyboards.main_menu(has_testing=False), parse_mode="HTML")
            await _notify_admins(bot, message.from_user, file_id=doc.file_id, is_doc=True)
        else:
            await message.answer("⚠️ Отправьте видео или ссылку.")

    @testing_router.message(SubmitStates.waiting_video, F.text)
    async def h_link(message: Message, state: FSMContext, bot: Bot):
        txt = message.text.strip()
        if not (txt.startswith("http://") or txt.startswith("https://")):
            await message.answer("⚠️ Видео или ссылку (http...).")
            return
        t = await testing_repo.get_active(message.from_user.id)
        await submission_repo.create(user_id=message.from_user.id, testing_id=t.id if t else None, link=txt)
        if t:
            await testing_repo.submit(message.from_user.id)
        await user_repo.set_status(message.from_user.id, "submitted")
        await state.clear()
        await message.answer(texts.LINK_SENT, reply_markup=keyboards.main_menu(has_testing=False), parse_mode="HTML")
        await _notify_admins(bot, message.from_user, link=txt)

    @testing_router.message(SubmitStates.waiting_video)
    async def h_other(message: Message):
        await message.answer("⚠️ Видео (60с, 10МБ) или ссылку GitHub.")

    # ===================== NDA =====================

    @nda_router.callback_query(F.data.startswith("nda_edit:"))
    async def cb_nda_edit(callback: CallbackQuery, state: FSMContext):
        fk = callback.data.split(":")[1]
        fl = dict(keyboards.NDA_FIELDS).get(fk, fk)
        data = await state.get_data()
        nda = data.get("nda_data", {})
        await state.set_state(NDAStates.editing_field)
        await state.update_data(editing_field=fk)
        hint = NDA_HINTS.get(fk, "")
        await safe_edit(callback.message,
            f"'<b>{fl}</b>'\nТекущее: {nda.get(fk, 'Не заполнено')}\n\n📍 {hint}\n\nВведите:",
            reply_markup=keyboards.nda_back_to_fields(), parse_mode="HTML")
        await callback.answer()

    @nda_router.callback_query(F.data == "nda_show_fields")
    async def cb_nda_fields(callback: CallbackQuery, state: FSMContext):
        await state.set_state(NDAStates.editing_fields)
        data = await state.get_data()
        await safe_edit(callback.message, "📋 <b>Данные:</b>",
                        reply_markup=keyboards.nda_fields(data.get("nda_data", {})), parse_mode="HTML")
        await callback.answer()

    @nda_router.message(NDAStates.editing_field, F.text)
    async def nda_value(message: Message, state: FSMContext):
        data = await state.get_data()
        fk = data.get("editing_field")
        nda = data.get("nda_data", {})
        value = message.text.strip()
        if fk == "iin" and (not value.isdigit() or len(value) != 12):
            await message.answer("⚠️ 12 цифр:")
            return
        if fk == "doc_number" and not value.upper().startswith("N"):
            await message.answer("⚠️ Начинается с N:")
            return
        nda[fk] = value
        await state.update_data(nda_data=nda)
        next_field = None
        found = False
        for k, l in keyboards.NDA_FIELDS:
            if k == fk:
                found = True
                continue
            if found and not nda.get(k):
                next_field = (k, l)
                break
        if next_field:
            await state.update_data(editing_field=next_field[0])
            hint = NDA_HINTS.get(next_field[0], "")
            await message.answer(
                f"'<b>{next_field[1]}</b>'\nТекущее: {nda.get(next_field[0], 'Не заполнено')}\n\n📍 {hint}\n\nВведите:",
                reply_markup=keyboards.nda_back_to_fields(), parse_mode="HTML")
        else:
            await state.set_state(NDAStates.editing_fields)
            await message.answer("📋 <b>Данные:</b>", reply_markup=keyboards.nda_fields(nda), parse_mode="HTML")

    @nda_router.callback_query(F.data == "nda_confirm")
    async def cb_nda_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot):
        data = await state.get_data()
        nda = data.get("nda_data", {})
        uid = callback.from_user.id
        required = ["last_name", "first_name", "iin", "phone", "email", "address"]
        missing = [dict(keyboards.NDA_FIELDS).get(f, f) for f in required if not nda.get(f)]
        if missing:
            await callback.answer(f"Заполните: {', '.join(missing)}", show_alert=True)
            return
        nda_id = await nda_repo.create(uid)
        fields = {k: v for k, v in nda.items() if k in [f[0] for f in keyboards.NDA_FIELDS] or k in ("front_photo_id", "back_photo_id")}
        fields["status"] = "completed"
        await nda_repo.update_fields(nda_id, **fields)
        await user_repo.set_status(uid, "nda_completed")
        iin = nda.get("iin", "unknown")
        output = f"data/nda_{iin}.docx"
        ok = NdaDocumentService.generate(nda, output)
        await state.clear()
        await safe_edit(callback.message, "✅ <b>NDA сгенерирован!</b>", parse_mode="HTML")
        if ok and os.path.exists(output):
            await bot.send_document(uid, document=FSInputFile(output, filename=f"NDA_{nda.get('last_name','')}.docx"), caption="✅ Ваш NDA")
        user = callback.from_user
        un = f"@{user.username}" if user.username else user.full_name
        txt = f"📄 <b>NDA #{nda_id}</b>\n👤 {nda.get('last_name','')} {nda.get('first_name','')}\n🆔 {nda.get('iin','')}\n📱 {nda.get('phone','')}\n🏷 {un}"
        for aid in settings.admin_ids:
            try:
                await bot.send_message(aid, txt, parse_mode="HTML")
                if ok and os.path.exists(output):
                    await bot.send_document(aid, document=FSInputFile(output))
                for key in ("front_photo_id", "back_photo_id"):
                    if nda.get(key):
                        await bot.send_photo(aid, photo=nda[key])
            except Exception as e:
                logger.error("NDA admin: %s", e)
        await callback.answer()

    # ===================== NDA CATCH =====================

    async def _download(bot: Bot, file_id: str) -> bytes:
        for i in range(3):
            try:
                f = await bot.get_file(file_id)
                r = await asyncio.wait_for(bot.download_file(f.file_path), timeout=60)
                return r.read()
            except Exception as e:
                logger.warning("Download %d: %s", i + 1, e)
                if i == 2:
                    raise
                await asyncio.sleep(2)

    @nda_catch_router.message(F.photo)
    async def catch_photo(message: Message, bot: Bot, state: FSMContext):
        uid = message.from_user.id
        user = await user_repo.get(uid)
        if not user:
            return
        if user.status == "awaiting_nda_front_photo":
            w = await message.answer("⏳ Распознаю...")
            nda = {"front_photo_id": message.photo[-1].file_id}
            try:
                photo_bytes = await _download(bot, message.photo[-1].file_id)
                result = await ocr.recognize_id_card(photo_bytes, "front")
                if result:
                    nda.update({k: v for k, v in result.items() if v})
            except Exception as e:
                logger.error("OCR front: %s", e)
                try:
                    await w.edit_text("⚠️ Не распознано. Заполните вручную.")
                except Exception:
                    pass
            await state.update_data(nda_data=nda)
            await user_repo.set_status(uid, "awaiting_nda_back_photo")
            try:
                await w.delete()
            except Exception:
                pass
            await message.answer(texts.ID_PHOTO_BACK, parse_mode="HTML")
        elif user.status == "awaiting_nda_back_photo":
            w = await message.answer("⏳ Распознаю...")
            data = await state.get_data()
            nda = data.get("nda_data", {})
            nda["back_photo_id"] = message.photo[-1].file_id
            try:
                photo_bytes = await _download(bot, message.photo[-1].file_id)
                result = await ocr.recognize_id_card(photo_bytes, "back")
                if result:
                    nda.update({k: v for k, v in result.items() if v})
            except Exception as e:
                logger.error("OCR back: %s", e)
                try:
                    await w.edit_text("⚠️ Не распознано. Заполните вручную.")
                except Exception:
                    pass
            await state.update_data(nda_data=nda)
            await user_repo.set_status(uid, "nda_editing")
            try:
                await w.delete()
            except Exception:
                pass
            await state.set_state(NDAStates.editing_fields)
            await message.answer("📋 <b>Данные:</b>", reply_markup=keyboards.nda_fields(nda), parse_mode="HTML")

    @nda_catch_router.message(F.text)
    async def catch_text(message: Message, state: FSMContext):
        uid = message.from_user.id
        user = await user_repo.get(uid)
        if not user:
            return
        cs = await state.get_state()
        if cs and "NDAStates" in str(cs):
            return
        if user.status == "awaiting_nda_front_photo":
            await message.answer("📸 Фото лицевой стороны.", parse_mode="HTML")
        elif user.status == "awaiting_nda_back_photo":
            await message.answer("📸 Фото оборотной стороны.", parse_mode="HTML")

    # ===================== ADMIN =====================

    @admin_router.message(Command("admin"))
    async def cmd_admin(message: Message):
        if not is_admin(message.from_user.id):
            await message.answer("⛔️ Нет доступа.")
            return
        await message.answer("🔐 <b>Админка</b>", reply_markup=keyboards.admin_menu(), parse_mode="HTML")

    @admin_router.callback_query(F.data == "admin_stats")
    async def cb_stats(callback: CallbackQuery):
        if not is_admin(callback.from_user.id):
            await callback.answer("Нет доступа!", show_alert=True)
            return
        s = await stats_repo.get_summary()
        txt = (f"📊 <b>Статистика</b>\n\n👥 {s.total_users}\n📅 {s.scheduled}\n🔄 {s.in_progress}\n"
               f"📩 {s.submitted}\n⏰ {s.expired}\n✅ {s.accepted}\n❌ {s.rejected}\n⏳ {s.pending_reviews}\n📄 {s.nda_completed}")
        await safe_edit(callback.message, txt, reply_markup=keyboards.admin_menu(), parse_mode="HTML")
        await callback.answer()

    @admin_router.callback_query(F.data == "admin_users")
    async def cb_users(callback: CallbackQuery):
        if not is_admin(callback.from_user.id):
            await callback.answer("Нет доступа!", show_alert=True)
            return
        users = await user_repo.get_all()
        if not users:
            await safe_edit(callback.message, "👥 Пусто.", reply_markup=keyboards.admin_menu(), parse_mode="HTML")
            await callback.answer()
            return
        txt = "👥 <b>Пользователи</b>\n\n"
        for i, u in enumerate(users[:20], 1):
            un = f"@{u.username}" if u.username else "—"
            txt += f"{i}. {u.full_name or '—'} ({un}) — {u.status} | {u.retry_count}\n"
        await safe_edit(callback.message, txt, reply_markup=keyboards.admin_menu(), parse_mode="HTML")
        await callback.answer()

    @admin_router.callback_query(F.data == "admin_testings")
    async def cb_testings(callback: CallbackQuery):
        if not is_admin(callback.from_user.id):
            await callback.answer("Нет доступа!", show_alert=True)
            return
        dates = await slot_repo.get_booked_dates()
        if not dates:
            await safe_edit(callback.message, "📝 Нет записей.", reply_markup=keyboards.admin_menu(), parse_mode="HTML")
            await callback.answer()
            return
        b = InlineKeyboardBuilder()
        for d in dates:
            b.row(InlineKeyboardButton(text=f"📅 {d['slot_date']} ({d['booked_count']})", callback_data=f"admin_day:{d['slot_date']}"))
        b.row(InlineKeyboardButton(text="🔙 Назад", callback_data="admin_back"))
        await safe_edit(callback.message, "📝 <b>Выберите день:</b>", reply_markup=b.as_markup(), parse_mode="HTML")
        await callback.answer()

    @admin_router.callback_query(F.data == "admin_back")
    async def cb_admin_back(callback: CallbackQuery):
        await safe_edit(callback.message, "🔐 <b>Админка</b>", reply_markup=keyboards.admin_menu(), parse_mode="HTML")
        await callback.answer()

    @admin_router.callback_query(F.data.startswith("admin_day:"))
    async def cb_admin_day(callback: CallbackQuery):
        if not is_admin(callback.from_user.id):
            await callback.answer("Нет доступа!", show_alert=True)
            return
        date_str = callback.data.split(":")[1]
        rows = await slot_repo.get_booked_details_by_date(date_str)
        status_emoji = {"scheduled":"📅","in_progress":"🔄","submitted":"📩","expired":"⏰","cancelled":"❌"}
        txt = f"📝 <b>{date_str}:</b>\n\n"
        for r in rows:
            st = status_emoji.get(r.status or "", "❓")
            name = r.full_name or "—"
            un = f" @{r.username}" if r.username else ""
            v = f" В{r.task_variant}" if r.task_variant else ""
            txt += f"{st} <b>{r.slot_start}–{r.slot_end}</b> | {name}{un}{v}\n"
        b = InlineKeyboardBuilder()
        b.row(InlineKeyboardButton(text="🔙 Даты", callback_data="admin_testings"))
        b.row(InlineKeyboardButton(text="🔐 Админка", callback_data="admin_back"))
        await safe_edit(callback.message, txt, reply_markup=b.as_markup(), parse_mode="HTML")
        await callback.answer()

    @admin_router.callback_query(F.data == "admin_submissions")
    async def cb_subs(callback: CallbackQuery):
        if not is_admin(callback.from_user.id):
            await callback.answer("Нет доступа!", show_alert=True)
            return
        subs = await submission_repo.get_pending()
        if not subs:
            await safe_edit(callback.message, "📩 Нет работ.", reply_markup=keyboards.admin_menu(), parse_mode="HTML")
            await callback.answer()
            return
        for sub in subs:
            variant = TaskService.get_variant_number(sub.user_id)
            txt = f"📩 <b>#{sub.id}</b>\n👤 {sub.full_name or sub.username or sub.user_id}\n📝 В{variant}"
            if sub.link:
                txt += f"\n🔗 {sub.link}"
            try:
                if sub.file_id and sub.file_type == "video":
                    await callback.bot.send_video(callback.from_user.id, video=sub.file_id, caption=txt,
                                                  reply_markup=keyboards.admin_review(sub.id), parse_mode="HTML")
                elif sub.file_id:
                    await callback.bot.send_document(callback.from_user.id, document=sub.file_id, caption=txt,
                                                     reply_markup=keyboards.admin_review(sub.id), parse_mode="HTML")
                else:
                    await callback.bot.send_message(callback.from_user.id, txt,
                                                    reply_markup=keyboards.admin_review(sub.id), parse_mode="HTML")
            except Exception as e:
                logger.error("Sub send: %s", e)
        await callback.answer()

    NDA_TEMPLATE_PATH = os.path.join(os.path.dirname(__file__), "static", "nda_template.docx")

    @admin_router.callback_query(F.data.startswith("review_accept:"))
    async def cb_accept(callback: CallbackQuery, bot: Bot):
        sub = await submission_repo.get_by_id(int(callback.data.split(":")[1]))
        if not sub:
            await callback.answer("Не найдено!", show_alert=True)
            return
        await submission_repo.review(sub.id, "accepted", callback.from_user.id)
        await user_repo.set_status(sub.user_id, "accepted")
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await callback.message.reply("✅ Принято!")
        await callback.answer("Принято!")
        try:
            await bot.send_message(sub.user_id, texts.ACCEPTED, parse_mode="HTML")
            await bot.send_message(sub.user_id, f"Группа: {settings.group_invite_link}")
            await bot.send_message(sub.user_id, texts.GROUP_WELCOME, parse_mode="HTML")
            await bot.send_message(sub.user_id, texts.NDA_INTRO, parse_mode="HTML")
            if os.path.exists(NDA_TEMPLATE_PATH):
                await bot.send_document(sub.user_id, document=FSInputFile(NDA_TEMPLATE_PATH, filename="NDA_Stratton.docx"))
            await bot.send_message(sub.user_id, texts.ID_PHOTO_FRONT, parse_mode="HTML")
            await user_repo.set_status(sub.user_id, "awaiting_nda_front_photo")
        except Exception as e:
            logger.error("Accept notify: %s", e)

    @admin_router.callback_query(F.data.startswith("review_reject:"))
    async def cb_reject(callback: CallbackQuery, bot: Bot):
        sub = await submission_repo.get_by_id(int(callback.data.split(":")[1]))
        if not sub:
            await callback.answer("Не найдено!", show_alert=True)
            return
        await submission_repo.review(sub.id, "rejected", callback.from_user.id)
        await user_repo.set_status(sub.user_id, "rejected")
        try:
            await callback.message.edit_reply_markup(reply_markup=None)
        except Exception:
            pass
        await callback.message.reply("❌ Отклонено.")
        await callback.answer("Отклонено!")
        try:
            await bot.send_message(sub.user_id, texts.REJECTED,
                                   reply_markup=keyboards.main_menu(has_testing=False), parse_mode="HTML")
        except Exception:
            pass

    @admin_router.callback_query(F.data == "admin_nda_search")
    async def cb_nda_search(callback: CallbackQuery, state: FSMContext):
        if not is_admin(callback.from_user.id):
            await callback.answer("Нет доступа!", show_alert=True)
            return
        await state.set_state(AdminStates.nda_search)
        await safe_edit(callback.message, "🔍 Введите имя, @username или ИИН:\n/cancel для отмены", parse_mode="HTML")
        await callback.answer()

    @admin_router.message(AdminStates.nda_search, Command("cancel"))
    async def cancel_nda(message: Message, state: FSMContext):
        await state.clear()
        await message.answer("❌", reply_markup=keyboards.admin_menu())

    @admin_router.message(AdminStates.nda_search, F.text)
    async def do_nda_search(message: Message, state: FSMContext, bot: Bot):
        query = message.text.strip().lower().replace("@", "")
        await state.clear()
        found = await nda_repo.search(query, user_repo)
        if not found:
            await message.answer(f"🔍 Не найдено: «{message.text.strip()}»", reply_markup=keyboards.admin_menu())
            return
        for n, u in found[:5]:
            name = f"{n.last_name} {n.first_name}".strip()
            un = f"@{u.username}" if u and u.username else "—"
            txt = f"📄 <b>NDA #{n.id}</b>\n👤 {name}\n🆔 {n.iin}\n📱 {n.phone}\n📧 {n.email}\n🏷 {un}"
            await message.answer(txt, parse_mode="HTML")
            path = f"data/nda_{n.iin}.docx"
            if os.path.exists(path):
                try:
                    await bot.send_document(message.from_user.id, document=FSInputFile(path))
                except Exception:
                    pass
            for photo_id in (n.front_photo_id, n.back_photo_id):
                if photo_id:
                    try:
                        await bot.send_photo(message.from_user.id, photo=photo_id)
                    except Exception:
                        pass
        await message.answer("🔐", reply_markup=keyboards.admin_menu())

    @admin_router.callback_query(F.data == "admin_export")
    async def cb_export(callback: CallbackQuery):
        if not is_admin(callback.from_user.id):
            await callback.answer("Нет доступа!", show_alert=True)
            return
        path = "data/users_export.csv"
        await user_repo.export_csv(path)
        await callback.bot.send_document(callback.from_user.id,
                                         document=FSInputFile(path, filename="users.csv"), caption="📤")
        await callback.answer()

    @admin_router.callback_query(F.data == "admin_broadcast")
    async def cb_bcast(callback: CallbackQuery, state: FSMContext):
        if not is_admin(callback.from_user.id):
            await callback.answer("Нет доступа!", show_alert=True)
            return
        await state.set_state(AdminStates.broadcast)
        await safe_edit(callback.message, "📢 Текст (/cancel):", parse_mode="HTML")
        await callback.answer()

    @admin_router.message(AdminStates.broadcast, Command("cancel"))
    async def cancel_bcast(message: Message, state: FSMContext):
        await state.clear()
        await message.answer("❌", reply_markup=keyboards.admin_menu())

    @admin_router.message(AdminStates.broadcast, F.text)
    async def do_bcast(message: Message, state: FSMContext):
        await state.clear()
        users = await user_repo.get_all()
        ok = err = 0
        for u in users:
            try:
                await message.bot.send_message(u.user_id, message.text, parse_mode="HTML")
                ok += 1
            except Exception:
                err += 1
        await message.answer(f"📢 {ok} ✅ / {err} ❌", reply_markup=keyboards.admin_menu())

    # ===================== TEST MODE =====================

    @test_router.message(Command("test"))
    async def cmd_test(message: Message, bot: Bot):
        if not is_admin(message.from_user.id):
            await message.answer("⛔️")
            return
        uid = message.from_user.id
        await message.answer("🧪 <b>ТЕСТ</b>", parse_mode="HTML")
        await message.answer(texts.ACCEPTED, parse_mode="HTML")
        await message.answer(f"Группа: {settings.group_invite_link}")
        await message.answer(texts.GROUP_WELCOME, parse_mode="HTML")
        await message.answer(texts.NDA_INTRO, parse_mode="HTML")
        if os.path.exists(NDA_TEMPLATE_PATH):
            await bot.send_document(uid, document=FSInputFile(NDA_TEMPLATE_PATH, filename="NDA.docx"))
        await message.answer(texts.ID_PHOTO_FRONT, parse_mode="HTML")
        await user_repo.set_status(uid, "awaiting_nda_front_photo")

    return [admin_router, test_router, start_router, testing_router, nda_router, nda_catch_router]
