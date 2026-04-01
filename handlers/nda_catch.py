import logging
import asyncio
from aiogram import Router, F, Bot
from aiogram.types import Message
from aiogram.fsm.context import FSMContext
from config import TEXTS
from keyboards.kb import nda_fields_kb
from utils.gemini import recognize_id_card
from handlers.nda import NDAStates

logger = logging.getLogger(__name__)
router = Router(name="nda_catch")


async def download_photo(bot: Bot, file_id: str, retries: int = 3) -> bytes:
    for i in range(retries):
        try:
            f = await bot.get_file(file_id)
            r = await asyncio.wait_for(bot.download_file(f.file_path), timeout=60)
            return r.read()
        except Exception as e:
            logger.warning("Download attempt %d: %s", i+1, e)
            if i == retries - 1: raise
            await asyncio.sleep(2)


@router.message(F.photo)
async def catch_photo(message: Message, db, bot: Bot, state: FSMContext):
    uid = message.from_user.id
    user = await db.get_user(uid)
    if not user: return
    status = user.get("status", "")

    if status == "awaiting_nda_front_photo":
        w = await message.answer("⏳ Распознаю...")
        photo = message.photo[-1]
        nda = {"front_photo_id": photo.file_id}
        try:
            b = await download_photo(bot, photo.file_id)
            r = await recognize_id_card(b, "front")
            if r:
                nda.update({k: v for k, v in r.items() if v})
                logger.info("OCR front: %s", r)
        except Exception as e:
            logger.error("Front OCR error: %s", e)
            try: await w.edit_text("⚠️ Не удалось распознать. Заполните вручную.")
            except: pass
        await state.update_data(nda_data=nda)
        await db.set_user_status(uid, "awaiting_nda_back_photo")
        try: await w.delete()
        except: pass
        await message.answer(TEXTS["id_back_photo_request"], parse_mode="HTML")

    elif status == "awaiting_nda_back_photo":
        w = await message.answer("⏳ Распознаю...")
        photo = message.photo[-1]
        data = await state.get_data()
        nda = data.get("nda_data", {})
        nda["back_photo_id"] = photo.file_id
        try:
            b = await download_photo(bot, photo.file_id)
            r = await recognize_id_card(b, "back")
            if r:
                nda.update({k: v for k, v in r.items() if v})
                logger.info("OCR back: %s", r)
        except Exception as e:
            logger.error("Back OCR error: %s", e)
            try: await w.edit_text("⚠️ Не удалось распознать. Заполните вручную.")
            except: pass
        await state.update_data(nda_data=nda)
        await db.set_user_status(uid, "nda_editing")
        try: await w.delete()
        except: pass
        await state.set_state(NDAStates.editing_fields)
        await message.answer("📋 <b>Данные:</b>\n\nПроверьте и отредактируйте:", reply_markup=nda_fields_kb(nda), parse_mode="HTML")


@router.message(F.text)
async def catch_text(message: Message, db, state: FSMContext):
    uid = message.from_user.id
    user = await db.get_user(uid)
    if not user: return
    cs = await state.get_state()
    if cs and "NDAStates" in str(cs): return
    status = user.get("status", "")
    if status == "awaiting_nda_front_photo":
        await message.answer("📸 Отправьте <b>фото</b> лицевой стороны.", parse_mode="HTML")
    elif status == "awaiting_nda_back_photo":
        await message.answer("📸 Отправьте <b>фото</b> оборотной стороны.", parse_mode="HTML")