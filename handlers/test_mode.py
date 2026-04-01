import logging
import os
from aiogram import Router, F, Bot
from aiogram.types import Message, FSInputFile
from aiogram.filters import Command
from config import TEXTS, ADMIN_IDS, GROUP_INVITE_LINK

logger = logging.getLogger(__name__)
router = Router(name="test_mode")
NDA_TEMPLATE = os.path.join(os.path.dirname(__file__), "..", "data", "nda_template.docx")


@router.message(Command("test"))
async def cmd_test(message: Message, db, bot: Bot):
    if message.from_user.id not in ADMIN_IDS:
        await message.answer("⛔️ Только для админов."); return
    uid = message.from_user.id
    await message.answer("🧪 <b>ТЕСТОВЫЙ РЕЖИМ</b>", parse_mode="HTML")
    await message.answer(TEXTS["accepted"], parse_mode="HTML")
    await message.answer(f"Группа: {GROUP_INVITE_LINK}")
    await message.answer(TEXTS["group_welcome"], parse_mode="HTML")
    await message.answer(TEXTS["nda_intro"], parse_mode="HTML")
    if os.path.exists(NDA_TEMPLATE):
        await bot.send_document(uid, document=FSInputFile(NDA_TEMPLATE, filename="NDA_Stratton.docx"), caption="📄 NDA")
    await message.answer(TEXTS["id_photo_request"], parse_mode="HTML")
    await db.set_user_status(uid, "awaiting_nda_front_photo")
