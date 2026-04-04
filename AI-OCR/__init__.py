import aiohttp
import json
import base64
import logging
from typing import Optional

logger = logging.getLogger(__name__)
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

class GeminiOCR:
    def __init__(self, api_key: str):
        self._api_key = api_key

    async def recognize_id_card(self, photo_bytes: bytes, side: str = "front") -> Optional[dict]:
        if not self._api_key or self._api_key == "YOUR_GEMINI_API_KEY_HERE":
            return None

        b64 = base64.b64encode(photo_bytes).decode()
        prompt = self._get_prompt(side)
        contents = [{"parts": [{"text": prompt}, {"inline_data": {"mime_type": "image/jpeg", "data": b64}}]}]
        text = await self._call(contents)
        if not text:
            return None
        return self._parse_json(text)

    async def _call(self, contents: list) -> Optional[str]:
        payload = {
            "contents": contents,
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2048},
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{GEMINI_URL}?key={self._api_key}",
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    if response.status != 200:
                        return None
                    data = await response.json()
                    candidates = data.get("candidates", [])
                    if candidates:
                        return candidates[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        except Exception as e:
            logger.error("Gemini error: %s", e)
        return None

    @staticmethod
    def _get_prompt(side: str) -> str:
        if side == "front":
            return (
                'Извлеки с фото казахстанского удостоверения (лицевая): '
                '{"last_name":"","first_name":"","middle_name":"","iin":"","doc_number":"","birth_date":"ДД.ММ.ГГГГ"}. '
                'Только JSON.'
            )
        return (
            'Извлеки с фото казахстанского удостоверения (оборотная): '
            '{"issuing_authority":"","nationality":"","birth_place":"","doc_expiry":"ДД.ММ.ГГГГ"}. '
            'Только JSON.'
        )

    @staticmethod
    def _parse_json(text: str) -> Optional[dict]:
        clean = text.strip()
        if clean.startswith("```"):
            clean = clean.split("\n", 1)[1] if "\n" in clean else clean[3:]
        if clean.endswith("```"):
            clean = clean[:-3]
        try:
            return json.loads(clean.strip())
        except json.JSONDecodeError:
            return None
