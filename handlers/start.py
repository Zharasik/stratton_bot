import logging
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from config import TEXTS, FAQ_ITEMS, get_task_variant_number
from keyboards.kb import main_menu_kb, back_to_main_kb, faq_kb

logger = logging.getLogger(__name__)
router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message, db):
    user = message.from_user
    await db.add_user(user.id, user.username, user.full_name)
    mention = f"@{user.username}" if user.username else user.full_name
    testing = await db.get_active_testing(user.id)
    await message.answer(TEXTS["welcome"].format(mention=mention), reply_markup=main_menu_kb(has_testing=bool(testing)), parse_mode="HTML")


@router.callback_query(F.data == "main_menu")
async def cb_main_menu(callback: CallbackQuery, db):
    testing = await db.get_active_testing(callback.from_user.id)
    await callback.message.edit_text(TEXTS["main_menu"], reply_markup=main_menu_kb(has_testing=bool(testing)), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "about_company")
async def cb_about(callback: CallbackQuery):
    await callback.message.edit_text(TEXTS["about_company"], reply_markup=back_to_main_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "contacts")
async def cb_contacts(callback: CallbackQuery):
    await callback.message.edit_text(TEXTS["contacts"], reply_markup=back_to_main_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "my_progress")
async def cb_progress(callback: CallbackQuery, db):
    uid = callback.from_user.id
    user = await db.get_user(uid)
    if not user:
        # Пользователь мог нажать кнопку до `/start`, поэтому запись в БД ещё не создана.
        await db.add_user(uid, callback.from_user.username, callback.from_user.full_name)
        user = await db.get_user(uid)
    status = user["status"] if user else "new"
    steps = {"step1": "⬜", "step2": "⬜", "step3": "⬜", "step4": "⬜", "step5": "⬜", "step6": "⬜"}
    if status in ("testing_scheduled",):
        steps["step1"] = "✅"
    elif status in ("in_progress",):
        steps["step1"] = "✅"; steps["step2"] = "✅"
    elif status in ("submitted",):
        steps["step1"] = "✅"; steps["step2"] = "✅"; steps["step3"] = "✅"
    elif status in ("accepted",):
        steps["step1"] = "✅"; steps["step2"] = "✅"; steps["step3"] = "✅"; steps["step4"] = "✅"
    elif status in ("awaiting_nda_front_photo", "awaiting_nda_back_photo", "nda_editing"):
        steps["step1"] = "✅"; steps["step2"] = "✅"; steps["step3"] = "✅"; steps["step4"] = "✅"; steps["step5"] = "🔄"
    elif status == "nda_completed":
        steps = {k: "✅" for k in steps}
    elif status == "rejected":
        steps["step1"] = "✅"; steps["step2"] = "✅"; steps["step3"] = "✅"; steps["step4"] = "❌"
    testing = await db.get_active_testing(uid)
    variant = get_task_variant_number(uid)
    extra = f"\n\n📝 Вариант задания: {variant}"
    if testing:
        extra += f"\n📅 Слот: {testing['slot_date']} {testing['slot_start']}"
    retry_count = user.get("retry_count", 0) if user else 0
    extra += f"\n🔄 Попытки: {retry_count}"
    text = TEXTS["status_tracker"].format(**steps) + extra
    await callback.message.edit_text(text, reply_markup=back_to_main_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "faq")
async def cb_faq(callback: CallbackQuery):
    await callback.message.edit_text("❓ <b>Частые вопросы</b>\n\nВыберите тему:", reply_markup=faq_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data.startswith("faq:"))
async def cb_faq_item(callback: CallbackQuery):
    key = callback.data.split(":")[1]
    answer = FAQ_ITEMS.get(key, "Информация не найдена.")
    await callback.message.edit_text(f"❓ <b>FAQ</b>\n\n{answer}", reply_markup=faq_kb(), parse_mode="HTML")
    await callback.answer()
