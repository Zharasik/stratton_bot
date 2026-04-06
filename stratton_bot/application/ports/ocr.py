from __future__ import annotations

from typing import Protocol, TypeVar

T = TypeVar("T")


class AIClient(Protocol):
    async def generate_json(self, *, prompt: str, image_bytes: bytes, mime_type: str = "image/jpeg") -> str: ...


class PromptBuilder(Protocol):
    def build(self, template_name: str) -> str: ...


class ResponseParser(Protocol):
    def parse(self, payload: str, schema: type[T]) -> T: ...
