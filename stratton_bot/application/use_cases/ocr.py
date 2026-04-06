from __future__ import annotations

from dataclasses import asdict

from stratton_bot.application.ports.ocr import AIClient, PromptBuilder, ResponseParser
from stratton_bot.domain.entities import IdentityCardBack, IdentityCardFront, OCRExtraction


class IdentityCardOCRUseCase:
    def __init__(self, ai_client: AIClient, prompt_builder: PromptBuilder, response_parser: ResponseParser) -> None:
        self._ai_client = ai_client
        self._prompt_builder = prompt_builder
        self._response_parser = response_parser

    async def recognize_front(self, image_bytes: bytes) -> OCRExtraction:
        prompt = self._prompt_builder.build("id_card_front")
        payload = await self._ai_client.generate_json(prompt=prompt, image_bytes=image_bytes)
        data = self._response_parser.parse(payload, IdentityCardFront)
        return OCRExtraction(side="front", payload=asdict(data))

    async def recognize_back(self, image_bytes: bytes) -> OCRExtraction:
        prompt = self._prompt_builder.build("id_card_back")
        payload = await self._ai_client.generate_json(prompt=prompt, image_bytes=image_bytes)
        data = self._response_parser.parse(payload, IdentityCardBack)
        return OCRExtraction(side="back", payload=asdict(data))
