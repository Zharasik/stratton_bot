from __future__ import annotations

import base64
import logging

import aiohttp

from stratton_bot.domain.exceptions import ConfigurationError, OCRProviderError

logger = logging.getLogger(__name__)


class GeminiAIClient:
    GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"

    def __init__(self, api_key: str) -> None:
        if not api_key:
            raise ConfigurationError("GEMINI_API_KEY is required for OCR")
        self._api_key = api_key

    async def generate_json(self, *, prompt: str, image_bytes: bytes, mime_type: str = "image/jpeg") -> str:
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": base64.b64encode(image_bytes).decode(),
                            }
                        },
                    ]
                }
            ],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2048},
        }
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"{self.GEMINI_URL}?key={self._api_key}",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=30),
            ) as response:
                if response.status != 200:
                    body = await response.text()
                    logger.error("Gemini request failed with status=%s body=%s", response.status, body)
                    raise OCRProviderError(f"Gemini request failed with status {response.status}")
                data = await response.json()
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as error:
            raise OCRProviderError("Gemini response does not contain text candidate") from error
