import logging
from datetime import datetime, timedelta
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import TEXTS, ADMIN_IDS, SLOT_START_HOUR, SLOT_END_HOUR, MAX_VIDEO_SIZE_BYTES, TASK_HOURS, MAX_RETRY_ATTEMPTS, get_task_for_user, get_task_variant_number
from keyboards.kb import calendar_kb, time_slots_kb, confirm_signup_kb, after_signup_kb, main_menu_kb, confirm_cancel_kb, back_to_main_kb, admin_review_kb
from database import now_local, TZ

logger = logging.getLogger(__name__)
router = Router(name="testing")
MONTHS_RU = {1:"января",2:"февраля",3:"марта",4:"апреля",5:"мая",6:"июня",7:"июля",8:"августа",9:"сентября",10:"октября",11:"ноября",12:"декабря"}


class SubmitStates(StatesGroup):
    waiting_video = State()


def is_within_task_window(slot_date: str, slot_start: str) -> bool:
    now = now_local()
    start_dt = datetime.strptime(f"{slot_date} {slot_start}", "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
    end_dt = start_dt + timedelta(hours=TASK_HOURS)
    return start_dt <= now <= end_dt


def get_deadline(slot_date: str, slot_start: str) -> str:
    start_dt = datetime.strptime(f"{slot_date} {slot_start}", "%Y-%m-%d %H:%M")
    return (start_dt + timedelta(hours=TASK_HOURS)).strftime("%H:%M")


@router.callback_query(F.data == "signup_start")
async def cb_signup(callback: CallbackQuery, db):
    uid = callback.from_user.id
    existing = await db.get_active_testing(uid)
    if existing:
        await callback.answer("Вы уже записаны!", show_alert=True)
        return
    retries = await db.get_retry_count(uid)
    if retries >= MAX_RETRY_ATTEMPTS:
        await callback.answer(f"Лимит попыток ({MAX_RETRY_ATTEMPTS}) исчерпан!", show_alert=True)
        return
    now = now_local()
    await callback.message.edit_text("📅 <b>Выберите дату:</b>\n\n🟢 свободно 🔴 занято [ ] сегодня", reply_markup=calendar_kb(now.year, now.month), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "cal_ignore")
async def cb_ign(callback: CallbackQuery):
    await callback.answer()

@router.callback_query(F.data == "slot_busy")
async def cb_busy(callback: CallbackQuery):
    await callback.answer("Занято.", show_alert=True)

@router.callback_query(F.data.startswith("cal_prev:"))
async def cb_prev(callback: CallbackQuery):
    _, y, m = callback.data.split(":"); y, m = int(y), int(m) - 1
    if m < 1: m, y = 12, y - 1
    await callback.message.edit_reply_markup(reply_markup=calendar_kb(y, m)); await callback.answer()

@router.callback_query(F.data.startswith("cal_next:"))
async def cb_next(callback: CallbackQuery):
    _, y, m = callback.data.split(":"); y, m = int(y), int(m) + 1
    if m > 12: m, y = 1, y + 1
    await callback.message.edit_reply_markup(reply_markup=calendar_kb(y, m)); await callback.answer()


@router.callback_query(F.data.startswith("pick_date:"))
async def cb_date(callback: CallbackQuery, db):
    date_str = callback.data.split(":")[1]
    await db.ensure_slots(date_str, SLOT_START_HOUR, SLOT_END_HOUR)
    slots = await db.get_all_slots(date_str)
    now = now_local()
    if date_str == now.strftime("%Y-%m-%d"):
        slots = [s for s in slots if int(s["slot_start"].split(":")[0]) >= now.hour + 1]
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    await callback.message.edit_text(f"🕐 <b>{dt.day} {MONTHS_RU[dt.month]} {dt.year}</b>\n\nВыберите час (задание на {TASK_HOURS}ч):", reply_markup=time_slots_kb(slots, date_str), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("pick_slot:"))
async def cb_slot(callback: CallbackQuery, db):
    slot = await db.get_slot(int(callback.data.split(":")[1]))
    if not slot or slot["booked_by"]:
        await callback.answer("Занято!", show_alert=True); return
    slot_start_dt = datetime.strptime(f"{slot['slot_date']} {slot['slot_start']}", "%Y-%m-%d %H:%M").replace(tzinfo=TZ)
    if slot_start_dt <= now_local():
        await callback.answer("Нельзя выбрать прошедшее время!", show_alert=True); return
    dt = datetime.strptime(slot["slot_date"], "%Y-%m-%d")
    dl = get_deadline(slot["slot_date"], slot["slot_start"])
    await callback.message.edit_text(f"📋 <b>Подтверждение:</b>\n\n📅 {dt.day} {MONTHS_RU[dt.month]} {dt.year}\n🕐 {slot['slot_start']}\n⏱ Дедлайн: {dl} ({TASK_HOURS}ч)\n\nПодтверждаете?", reply_markup=confirm_signup_kb(slot["id"]), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("confirm_slot:"))
async def cb_confirm(callback: CallbackQuery, db):
    slot_id = int(callback.data.split(":")[1])
    uid = callback.from_user.id
    if not await db.book_slot(slot_id, uid):
        await callback.answer("Слот недоступен или уже прошёл!", show_alert=True); return
    variant = get_task_variant_number(uid)
    await db.create_testing(uid, slot_id, variant)
    await db.set_user_status(uid, "testing_scheduled")
    await db.increment_retry(uid)
    slot = await db.get_slot(slot_id)
    dt = datetime.strptime(slot["slot_date"], "%Y-%m-%d")
    dl = get_deadline(slot["slot_date"], slot["slot_start"])
    await callback.message.edit_text(TEXTS["signup_success"].format(date=dt.strftime("%d.%m.%Y"), time_start=slot["slot_start"], time_end=dl), reply_markup=after_signup_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "remind_testing")
async def cb_remind(callback: CallbackQuery, db):
    t = await db.get_active_testing(callback.from_user.id)
    if not t: await callback.answer("Нет записей!", show_alert=True); return
    dt = datetime.strptime(t["slot_date"], "%Y-%m-%d")
    dl = get_deadline(t["slot_date"], t["slot_start"])
    active = is_within_task_window(t["slot_date"], t["slot_start"])
    if active:
        end_dt = datetime.strptime(f"{t['slot_date']} {t['slot_start']}", "%Y-%m-%d %H:%M") + timedelta(hours=TASK_HOURS)
        mins = max(0, int((end_dt.replace(tzinfo=TZ) - now_local()).total_seconds() // 60))
        st = f"🟢 Активно! Осталось {mins} мин"
    else:
        st = "⏳ Ожидание"
    await callback.message.edit_text(f"📅 <b>Запись:</b>\n\n📅 {dt.strftime('%d.%m.%Y')}\n🕐 {t['slot_start']}\n⏱ До {dl}\n📌 {st}", reply_markup=after_signup_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "cancel_testing")
async def cb_cancel(callback: CallbackQuery):
    await callback.message.edit_text("⚠️ Отменить?", reply_markup=confirm_cancel_kb(), parse_mode="HTML"); await callback.answer()

@router.callback_query(F.data == "confirm_cancel")
async def cb_do_cancel(callback: CallbackQuery, db):
    await db.cancel_testing(callback.from_user.id)
    await db.set_user_status(callback.from_user.id, "cancelled")
    await callback.message.edit_text("❌ Отменено.", reply_markup=main_menu_kb(has_testing=False), parse_mode="HTML"); await callback.answer()


@router.callback_query(F.data == "detailed_info_task")
async def cb_detail(callback: CallbackQuery, db):
    t = await db.get_active_testing(callback.from_user.id)
    if not t: await callback.answer("Нет тестирования!", show_alert=True); return
    if not is_within_task_window(t["slot_date"], t["slot_start"]):
        dt = datetime.strptime(t["slot_date"], "%Y-%m-%d")
        await callback.message.edit_text(TEXTS["task_not_yet"].format(date=dt.strftime("%d.%m.%Y"), time_start=t["slot_start"]), reply_markup=after_signup_kb(), parse_mode="HTML")
        await callback.answer(); return
    dl = get_deadline(t["slot_date"], t["slot_start"])
    task = get_task_for_user(callback.from_user.id)
    await callback.message.edit_text(f"⏰ <b>Дедлайн: {dl}</b>\n\n{task}", reply_markup=back_to_main_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "submit_start")
async def cb_submit(callback: CallbackQuery, state: FSMContext, db):
    t = await db.get_active_testing(callback.from_user.id)
    if not t: await callback.answer("Нет тестирования!", show_alert=True); return
    if not is_within_task_window(t["slot_date"], t["slot_start"]):
        dl = get_deadline(t["slot_date"], t["slot_start"])
        await callback.answer(f"Доступно с {t['slot_start']} до {dl}", show_alert=True); return
    await state.set_state(SubmitStates.waiting_video)
    await callback.message.edit_text(TEXTS["video_request"], reply_markup=back_to_main_kb(), parse_mode="HTML"); await callback.answer()


async def _send_to_admins(bot: Bot, db, user, file_id: str = None, link: str = None, is_doc: bool = False):
    un = f"@{user.username}" if user.username else user.full_name
    variant = get_task_variant_number(user.id)
    cap = f"📩 <b>Новая работа!</b>\n\n👤 {user.full_name} ({un})\n🆔 <code>{user.id}</code>\n📝 Вариант: {variant}\n📅 {now_local().strftime('%d.%m.%Y %H:%M')}"
    if link: cap += f"\n🔗 {link}"
    subs = await db.get_pending_submissions()
    sub_id = subs[0]["id"] if subs else 0
    for aid in ADMIN_IDS:
        try:
            if file_id and is_doc:
                await bot.send_document(aid, document=file_id, caption=cap, reply_markup=admin_review_kb(sub_id), parse_mode="HTML")
            elif file_id:
                await bot.send_video(aid, video=file_id, caption=cap, reply_markup=admin_review_kb(sub_id), parse_mode="HTML")
            else:
                await bot.send_message(aid, cap, reply_markup=admin_review_kb(sub_id), parse_mode="HTML")
        except Exception as e:
            logger.error("Admin send error %s: %s", aid, e)


@router.message(SubmitStates.waiting_video, F.video)
async def h_video(message: Message, state: FSMContext, db, bot: Bot):
    v = message.video
    if v.file_size and v.file_size > MAX_VIDEO_SIZE_BYTES:
        await message.answer(TEXTS["video_too_big"]); return
    t = await db.get_active_testing(message.from_user.id)
    await db.add_submission(user_id=message.from_user.id, testing_id=t["id"] if t else None, file_id=v.file_id, file_type="video", file_size=v.file_size)
    if t: await db.submit_testing(message.from_user.id)
    await db.set_user_status(message.from_user.id, "submitted")
    await state.clear()
    await message.answer(TEXTS["video_sent"], reply_markup=main_menu_kb(has_testing=False), parse_mode="HTML")
    await _send_to_admins(bot, db, message.from_user, file_id=v.file_id)

@router.message(SubmitStates.waiting_video, F.video_note)
async def h_vnote(message: Message):
    await message.answer("⚠️ Обычное видео, не кружок.")

@router.message(SubmitStates.waiting_video, F.document)
async def h_doc(message: Message, state: FSMContext, db, bot: Bot):
    d = message.document
    if d.mime_type and d.mime_type.startswith("video/"):
        if d.file_size and d.file_size > MAX_VIDEO_SIZE_BYTES:
            await message.answer(TEXTS["video_too_big"]); return
        t = await db.get_active_testing(message.from_user.id)
        await db.add_submission(user_id=message.from_user.id, testing_id=t["id"] if t else None, file_id=d.file_id, file_type="document_video", file_size=d.file_size)
        if t: await db.submit_testing(message.from_user.id)
        await db.set_user_status(message.from_user.id, "submitted")
        await state.clear()
        await message.answer(TEXTS["video_sent"], reply_markup=main_menu_kb(has_testing=False), parse_mode="HTML")
        await _send_to_admins(bot, db, message.from_user, file_id=d.file_id, is_doc=True)
    else:
        await message.answer("⚠️ Отправьте видео или ссылку.")

@router.message(SubmitStates.waiting_video, F.text)
async def h_link(message: Message, state: FSMContext, db, bot: Bot):
    txt = message.text.strip()
    if txt.startswith("http://") or txt.startswith("https://") or txt.startswith("t.me/"):
        t = await db.get_active_testing(message.from_user.id)
        await db.add_submission(user_id=message.from_user.id, testing_id=t["id"] if t else None, link=txt)
        if t: await db.submit_testing(message.from_user.id)
        await db.set_user_status(message.from_user.id, "submitted")
        await state.clear()
        await message.answer(TEXTS["link_sent"], reply_markup=main_menu_kb(has_testing=False), parse_mode="HTML")
        await _send_to_admins(bot, db, message.from_user, link=txt)
    else:
        await message.answer("⚠️ Отправьте видео или ссылку (http...).")

@router.message(SubmitStates.waiting_video)
async def h_other(message: Message):
    await message.answer("⚠️ Видео (до 60с, 10МБ) или ссылку на GitHub.", parse_mode="HTML")
