import logging
import os
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import ADMIN_IDS, TEXTS, GROUP_INVITE_LINK, get_task_variant_number
from keyboards.kb import admin_menu_kb, admin_review_kb, main_menu_kb

logger = logging.getLogger(__name__)
router = Router(name="admin")
NDA_TEMPLATE = os.path.join(os.path.dirname(__file__), "..", "data", "nda_template.docx")


class AdminStates(StatesGroup):
    broadcast_message = State()
    nda_search = State()


def check_admin(uid: int) -> bool:
    return uid in ADMIN_IDS


async def safe_edit(message, text, **kwargs):
    try:
        await message.edit_text(text, **kwargs)
    except Exception:
        pass


@router.message(Command("admin"))
async def cmd_admin(message: Message):
    if not check_admin(message.from_user.id):
        await message.answer("⛔️ Нет доступа."); return
    await message.answer("🔐 <b>Панель администратора</b>", reply_markup=admin_menu_kb(), parse_mode="HTML")


@router.callback_query(F.data == "admin_stats")
async def cb_stats(callback: CallbackQuery, db):
    if not check_admin(callback.from_user.id): await callback.answer("Нет доступа!", show_alert=True); return
    s = await db.get_stats_summary()
    text = (
        f"📊 <b>Статистика</b>\n\n"
        f"👥 Пользователей: {s['total_users']}\n"
        f"📅 Записаны: {s['scheduled']}\n"
        f"🔄 В процессе: {s['in_progress']}\n"
        f"📩 Отправили: {s['submitted']}\n"
        f"⏰ Истекло: {s['expired']}\n"
        f"✅ Принято: {s['accepted']}\n"
        f"❌ Отклонено: {s['rejected']}\n"
        f"⏳ На проверке: {s['pending_reviews']}\n"
        f"📄 NDA: {s['nda_completed']}"
    )
    await safe_edit(callback.message, text, reply_markup=admin_menu_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_users")
async def cb_users(callback: CallbackQuery, db):
    if not check_admin(callback.from_user.id): await callback.answer("Нет доступа!", show_alert=True); return
    users = await db.get_all_users()
    if not users:
        await safe_edit(callback.message, "👥 Нет пользователей.", reply_markup=admin_menu_kb(), parse_mode="HTML")
        await callback.answer(); return
    text = "👥 <b>Пользователи</b>\n\n"
    for i, u in enumerate(users[:20], 1):
        un = f"@{u['username']}" if u.get('username') else "—"
        name = u.get('full_name') or '—'
        status = u.get('status', '—')
        retry = u.get('retry_count', 0)
        text += f"{i}. {name} ({un})\n   Статус: {status} | Попытки: {retry}\n"
    if len(users) > 20:
        text += f"\n... +{len(users)-20}"
    await safe_edit(callback.message, text, reply_markup=admin_menu_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_testings")
async def cb_testings(callback: CallbackQuery, db):
    if not check_admin(callback.from_user.id): await callback.answer("Нет доступа!", show_alert=True); return
    dates = await db.get_booked_dates()
    if not dates:
        await safe_edit(callback.message, "📝 Нет записей.", reply_markup=admin_menu_kb(), parse_mode="HTML")
        await callback.answer(); return
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    b = InlineKeyboardBuilder()
    for d in dates:
        b.row(InlineKeyboardButton(text=f"📅 {d['slot_date']} ({d['booked_count']} чел.)", callback_data=f"admin_day:{d['slot_date']}"))
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data="admin_menu_back"))
    await safe_edit(callback.message, "📝 <b>Выберите день:</b>", reply_markup=b.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_menu_back")
async def cb_admin_back(callback: CallbackQuery):
    await safe_edit(callback.message, "🔐 <b>Панель администратора</b>", reply_markup=admin_menu_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("admin_day:"))
async def cb_admin_day(callback: CallbackQuery, db):
    if not check_admin(callback.from_user.id): await callback.answer("Нет доступа!", show_alert=True); return
    date_str = callback.data.split(":")[1]
    rows = await db.get_booked_slots_by_date(date_str)
    if not rows:
        await safe_edit(callback.message, f"📅 <b>{date_str}</b>\n\nНет записей на этот день.", reply_markup=admin_menu_kb(), parse_mode="HTML")
        await callback.answer(); return
    status_emoji = {"scheduled": "📅", "in_progress": "🔄", "submitted": "📩", "expired": "⏰", "cancelled": "❌"}
    text = f"📝 <b>Записи на {date_str}:</b>\n\n"
    for r in rows:
        name = r.get("full_name") or "—"
        un = f" @{r['username']}" if r.get("username") else ""
        st = status_emoji.get(r.get("status", ""), "❓")
        variant = f" В{r['task_variant']}" if r.get("task_variant") else ""
        text += f"{st} <b>{r['slot_start']}–{r['slot_end']}</b> | {name}{un}{variant}\n"
    from aiogram.utils.keyboard import InlineKeyboardBuilder
    from aiogram.types import InlineKeyboardButton
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔙 К датам", callback_data="admin_testings"))
    b.row(InlineKeyboardButton(text="🔐 Админка", callback_data="admin_menu_back"))
    await safe_edit(callback.message, text, reply_markup=b.as_markup(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "admin_submissions")
async def cb_subs(callback: CallbackQuery, db):
    if not check_admin(callback.from_user.id): await callback.answer("Нет доступа!", show_alert=True); return
    subs = await db.get_pending_submissions()
    if not subs:
        await safe_edit(callback.message, "📩 Нет работ на проверке.", reply_markup=admin_menu_kb(), parse_mode="HTML")
        await callback.answer(); return
    for sub in subs:
        name = sub.get("full_name") or sub.get("username") or f"ID:{sub['user_id']}"
        variant = get_task_variant_number(sub["user_id"])
        text = f"📩 <b>#{sub['id']}</b>\n👤 {name}\n📝 Вариант: {variant}\n📅 {sub['submitted_at']}"
        if sub.get("link"): text += f"\n🔗 {sub['link']}"
        try:
            if sub.get("file_id") and sub.get("file_type") == "video":
                await callback.bot.send_video(callback.from_user.id, video=sub["file_id"], caption=text, reply_markup=admin_review_kb(sub["id"]), parse_mode="HTML")
            elif sub.get("file_id"):
                await callback.bot.send_document(callback.from_user.id, document=sub["file_id"], caption=text, reply_markup=admin_review_kb(sub["id"]), parse_mode="HTML")
            else:
                await callback.bot.send_message(callback.from_user.id, text=text, reply_markup=admin_review_kb(sub["id"]), parse_mode="HTML")
        except Exception as e:
            logger.error("Sub send: %s", e)
    await callback.answer()


@router.callback_query(F.data == "admin_nda_search")
async def cb_nda_search(callback: CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id): await callback.answer("Нет доступа!", show_alert=True); return
    await state.set_state(AdminStates.nda_search)
    await safe_edit(callback.message, "🔍 <b>Поиск NDA</b>\n\nВведите имя, @username или ИИН:\n/cancel для отмены", parse_mode="HTML")
    await callback.answer()


@router.message(AdminStates.nda_search, Command("cancel"))
async def cancel_nda(message: Message, state: FSMContext):
    await state.clear(); await message.answer("❌ Отменено.", reply_markup=admin_menu_kb())


@router.message(AdminStates.nda_search, F.text)
async def do_nda_search(message: Message, state: FSMContext, db, bot: Bot):
    q = message.text.strip().lower().replace("@", "")
    await state.clear()
    ndas = await db.get_all_ndas()
    found = []
    for n in ndas:
        s = f"{n.get('last_name','')} {n.get('first_name','')} {n.get('middle_name','')} {n.get('iin','')}".lower()
        u = await db.get_user(n["user_id"])
        if u: s += f" {u.get('username','')} {u.get('full_name','')}".lower()
        if q in s: found.append((n, u))
    if not found:
        await message.answer(f"🔍 Не найдено: «{message.text.strip()}»", reply_markup=admin_menu_kb()); return
    for n, u in found[:5]:
        name = f"{n.get('last_name','')} {n.get('first_name','')}".strip()
        un = f"@{u['username']}" if u and u.get("username") else "—"
        text = f"📄 <b>NDA #{n['id']}</b>\n\n👤 {name}\n🆔 ИИН: {n.get('iin','—')}\n📱 {n.get('phone','—')}\n📧 {n.get('email','—')}\n📍 {n.get('address','—')}\n🏷 {un}\n📅 {n.get('created_at','—')}"
        await message.answer(text, parse_mode="HTML")
        path = f"data/nda_{n.get('iin','unknown')}.docx"
        if os.path.exists(path):
            try: await bot.send_document(message.from_user.id, document=FSInputFile(path, filename=f"NDA_{name}.docx"))
            except: pass
        for key in ("front_photo_id", "back_photo_id"):
            if n.get(key):
                try: await bot.send_photo(message.from_user.id, photo=n[key], caption="📸 " + ("Лицевая" if "front" in key else "Оборотная"))
                except: pass
    await message.answer("🔐 Админка", reply_markup=admin_menu_kb())


@router.callback_query(F.data == "admin_export")
async def cb_export(callback: CallbackQuery, db):
    if not check_admin(callback.from_user.id): await callback.answer("Нет доступа!", show_alert=True); return
    path = "data/users_export.csv"
    await db.export_users_csv(path)
    await callback.bot.send_document(callback.from_user.id, document=FSInputFile(path, filename="users_export.csv"), caption="📤 Экспорт")
    await callback.answer()


@router.callback_query(F.data.startswith("review_accept:"))
async def cb_accept(callback: CallbackQuery, db, bot: Bot):
    sub = await db.get_submission(int(callback.data.split(":")[1]))
    if not sub: await callback.answer("Не найдено!", show_alert=True); return
    await db.review_submission(sub["id"], "accepted", callback.from_user.id)
    await db.set_user_status(sub["user_id"], "accepted")
    try: await callback.message.edit_reply_markup(reply_markup=None)
    except: pass
    await callback.message.reply("✅ Принято!"); await callback.answer("Принято!")
    uid = sub["user_id"]
    try:
        await bot.send_message(uid, TEXTS["accepted"], parse_mode="HTML")
        await bot.send_message(uid, f"Группа стажеров: {GROUP_INVITE_LINK}\n\nПрисоединяйтесь!")
        await bot.send_message(uid, TEXTS["group_welcome"], parse_mode="HTML")
        await bot.send_message(uid, TEXTS["nda_intro"], parse_mode="HTML")
        if os.path.exists(NDA_TEMPLATE):
            await bot.send_document(uid, document=FSInputFile(NDA_TEMPLATE, filename="NDA_Stratton.docx"), caption="📄 NDA для ознакомления")
        await bot.send_message(uid, TEXTS["id_photo_request"], parse_mode="HTML")
        await db.set_user_status(uid, "awaiting_nda_front_photo")
    except Exception as e:
        logger.error("Notify %s: %s", uid, e)


@router.callback_query(F.data.startswith("review_reject:"))
async def cb_reject(callback: CallbackQuery, db, bot: Bot):
    sub = await db.get_submission(int(callback.data.split(":")[1]))
    if not sub: await callback.answer("Не найдено!", show_alert=True); return
    await db.review_submission(sub["id"], "rejected", callback.from_user.id)
    await db.set_user_status(sub["user_id"], "rejected")
    try: await callback.message.edit_reply_markup(reply_markup=None)
    except: pass
    await callback.message.reply("❌ Отклонено."); await callback.answer("Отклонено!")
    try: await bot.send_message(sub["user_id"], TEXTS["rejected"], reply_markup=main_menu_kb(has_testing=False), parse_mode="HTML")
    except: pass


@router.callback_query(F.data == "admin_broadcast")
async def cb_bcast(callback: CallbackQuery, state: FSMContext):
    if not check_admin(callback.from_user.id): await callback.answer("Нет доступа!", show_alert=True); return
    await state.set_state(AdminStates.broadcast_message)
    await safe_edit(callback.message, "📢 Текст рассылки (/cancel):", parse_mode="HTML"); await callback.answer()

@router.message(AdminStates.broadcast_message, Command("cancel"))
async def cancel_bcast(message: Message, state: FSMContext):
    await state.clear(); await message.answer("❌", reply_markup=admin_menu_kb())

@router.message(AdminStates.broadcast_message, F.text)
async def do_bcast(message: Message, state: FSMContext, db):
    await state.clear()
    users = await db.get_all_users()
    s = f = 0
    for u in users:
        try: await message.bot.send_message(u["user_id"], message.text, parse_mode="HTML"); s += 1
        except: f += 1
    await message.answer(f"📢 Отправлено: {s}, ошибок: {f}", reply_markup=admin_menu_kb(), parse_mode="HTML")