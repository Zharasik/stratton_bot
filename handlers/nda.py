import logging
import os
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, FSInputFile
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from config import TEXTS, ADMIN_IDS
from keyboards.kb import nda_fields_kb, nda_cancel_edit_kb, NDA_FIELDS
from utils.gemini import recognize_id_card
from utils.nda_gen import generate_nda

logger = logging.getLogger(__name__)
router = Router(name="nda")


class NDAStates(StatesGroup):
    waiting_front_photo = State()
    waiting_back_photo = State()
    editing_fields = State()
    editing_field = State()


NDA_HINTS = {
    "last_name": "📍 Фамилия на русском", "first_name": "📍 Имя на русском",
    "middle_name": "📍 Отчество на русском", "iin": "📍 12 цифр",
    "doc_number": "📍 Номер документа как в удостоверении", "birth_date": "📍 ДД.ММ.ГГГГ",
    "issuing_authority": "📍 Оборотная сторона", "phone": "📍 +7 777 123 4567",
    "email": "📍 Ваш email", "address": "📍 Адрес проживания",
    "nationality": "📍 Оборотная сторона", "birth_place": "📍 Оборотная сторона",
    "doc_expiry": "📍 ДД.ММ.ГГГГ",
}


@router.callback_query(F.data.startswith("nda_edit:"))
async def cb_edit(callback: CallbackQuery, state: FSMContext):
    fk = callback.data.split(":")[1]
    fl = dict(NDA_FIELDS).get(fk, fk)
    data = await state.get_data()
    nda = data.get("nda_data", {})
    await state.set_state(NDAStates.editing_field)
    await state.update_data(editing_field=fk)
    await callback.message.edit_text(f"'<b>{fl}</b>'\nТекущее: {nda.get(fk, 'Не заполнено')}\n\n{NDA_HINTS.get(fk, '')}\n\nВведите:", reply_markup=nda_cancel_edit_kb(), parse_mode="HTML")
    await callback.answer()


@router.callback_query(F.data == "nda_show_fields")
async def cb_fields(callback: CallbackQuery, state: FSMContext):
    await state.set_state(NDAStates.editing_fields)
    data = await state.get_data()
    await callback.message.edit_text("📋 <b>Данные:</b>\n\nПроверьте и отредактируйте:", reply_markup=nda_fields_kb(data.get("nda_data", {})), parse_mode="HTML")
    await callback.answer()


@router.message(NDAStates.editing_field, F.text)
async def field_val(message: Message, state: FSMContext):
    data = await state.get_data()
    fk = data.get("editing_field")
    nda = data.get("nda_data", {})
    v = message.text.strip()
    if fk == "iin" and (not v.isdigit() or len(v) != 12):
        await message.answer("⚠️ 12 цифр:"); return
    nda[fk] = v
    await state.update_data(nda_data=nda)
    nxt = None
    found = False
    for k, l in NDA_FIELDS:
        if k == fk: found = True; continue
        if found and not nda.get(k): nxt = (k, l); break
    if nxt:
        await state.update_data(editing_field=nxt[0])
        await message.answer(f"'<b>{nxt[1]}</b>'\nТекущее: {nda.get(nxt[0], 'Не заполнено')}\n\n{NDA_HINTS.get(nxt[0], '')}\n\nВведите:", reply_markup=nda_cancel_edit_kb(), parse_mode="HTML")
    else:
        await state.set_state(NDAStates.editing_fields)
        await message.answer("📋 <b>Данные:</b>", reply_markup=nda_fields_kb(nda), parse_mode="HTML")


@router.callback_query(F.data == "nda_confirm")
async def cb_confirm(callback: CallbackQuery, state: FSMContext, db, bot: Bot):
    data = await state.get_data()
    nda = data.get("nda_data", {})
    uid = callback.from_user.id
    required = ["last_name", "first_name", "iin", "phone", "email", "address"]
    missing = [dict(NDA_FIELDS).get(f, f) for f in required if not nda.get(f)]
    if missing:
        await callback.answer(f"Заполните: {', '.join(missing)}", show_alert=True); return
    nda_id = await db.create_nda(uid)
    fields = {k: v for k, v in nda.items() if k in [f[0] for f in NDA_FIELDS] or k in ("front_photo_id", "back_photo_id")}
    fields["status"] = "completed"
    await db.update_nda(nda_id, **fields)
    await db.set_user_status(uid, "nda_completed")
    iin = nda.get("iin", "unknown")
    path = f"data/nda_{iin}.docx"
    ok = generate_nda(nda, path)
    await state.clear()
    await callback.message.edit_text("✅ <b>NDA сгенерирован!</b>\nАдминистратор получил документ.", parse_mode="HTML")
    if ok and os.path.exists(path):
        await bot.send_document(uid, document=FSInputFile(path, filename=f"NDA_{nda.get('last_name','')}.docx"), caption="✅ Ваш NDA")
    user = callback.from_user
    un = f"@{user.username}" if user.username else user.full_name
    txt = f"📄 <b>NDA #{nda_id}</b>\n\n👤 {nda.get('last_name','')} {nda.get('first_name','')}\n🆔 {nda.get('iin','')}\n📱 {nda.get('phone','')}\n📧 {nda.get('email','')}\n🏷 {un} (<code>{uid}</code>)"
    for aid in ADMIN_IDS:
        try:
            await bot.send_message(aid, txt, parse_mode="HTML")
            if ok and os.path.exists(path):
                await bot.send_document(aid, document=FSInputFile(path, filename=f"NDA_{iin}.docx"))
            for key in ("front_photo_id", "back_photo_id"):
                if nda.get(key):
                    await bot.send_photo(aid, photo=nda[key], caption="📸 " + ("Лицевая" if "front" in key else "Оборотная"))
        except Exception as e:
            logger.error("NDA admin send error %s: %s", aid, e)
    await callback.answer()