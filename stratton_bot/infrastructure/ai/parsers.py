from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from typing import Any, TypeVar

from stratton_bot.domain.exceptions import OCRResponseError

T = TypeVar("T")


class JsonResponseParser:
    def parse(self, payload: str, schema: type[T]) -> T:
        if not is_dataclass(schema):
            raise OCRResponseError(f"Schema {schema} must be a dataclass")
        cleaned = payload.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]
        try:
            raw_data = json.loads(cleaned.strip())
        except json.JSONDecodeError as error:
            raise OCRResponseError("OCR provider returned invalid JSON") from error
        allowed = {field.name for field in fields(schema)}
        values: dict[str, Any] = {name: raw_data.get(name, "") for name in allowed}
        return schema(**values)
