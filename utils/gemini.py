import aiohttp
import json
import base64
import logging
from typing import Optional
from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent"


async def _call_gemini(contents: list, temperature: float = 0.1) -> Optional[str]:
    if not GEMINI_API_KEY or GEMINI_API_KEY == "YOUR_GEMINI_API_KEY_HERE":
        return None
    try:
        async with aiohttp.ClientSession() as s:
            async with s.post(f"{GEMINI_URL}?key={GEMINI_API_KEY}",
                json={"contents": contents, "generationConfig": {"temperature": temperature, "maxOutputTokens": 2048}},
                timeout=aiohttp.ClientTimeout(total=30)) as r:
                if r.status != 200:
                    return None
                d = await r.json()
                c = d.get("candidates", [])
                if c:
                    return c[0].get("content", {}).get("parts", [{}])[0].get("text", "")
    except Exception as e:
        logger.error("Gemini: %s", e)
    return None


async def recognize_id_card(photo_bytes: bytes, side: str = "front") -> Optional[dict]:
    b64 = base64.b64encode(photo_bytes).decode()
    if side == "front":
        p = 'Извлеки с фото казахстанского удостоверения (лицевая): {"last_name":"","first_name":"","middle_name":"","iin":"","doc_number":"","birth_date":"ДД.ММ.ГГГГ"}. Если поле не видно, верни пустую строку. Только JSON.'
    else:
        p = (
            'Извлеки с фото казахстанского удостоверения (оборотная): '
            '{"issuing_authority":"","nationality":"","birth_place":"","doc_expiry":"ДД.ММ.ГГГГ","doc_number":""}. '
            'Номер документа ищи в верхнем правом углу оборотной стороны. '
            'Если поле не видно, верни пустую строку. Только JSON.'
        )
    r = await _call_gemini([{"parts": [{"text": p}, {"inline_data": {"mime_type": "image/jpeg", "data": b64}}]}])
    if not r:
        return None
    try:
        c = r.strip()
        if c.startswith("```"):
            c = c.split("\n", 1)[1] if "\n" in c else c[3:]
        if c.endswith("```"):
            c = c[:-3]
        return json.loads(c.strip())
    except:
        return None