from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class Localizer:
    def __init__(self, locale: str, payload: dict[str, Any]) -> None:
        self.locale = locale
        self._payload = payload

    def text(self, key: str, **kwargs: Any) -> str:
        value = self._resolve(key)
        if not isinstance(value, str):
            raise KeyError(f"Translation key '{key}' does not contain a string")
        return value.format(**kwargs)

    def mapping(self, key: str) -> dict[str, Any]:
        value = self._resolve(key)
        if not isinstance(value, dict):
            raise KeyError(f"Translation key '{key}' does not contain a mapping")
        return value

    def _resolve(self, key: str) -> Any:
        current: Any = self._payload
        for part in key.split("."):
            current = current[part]
        return current


class Translator:
    def __init__(self, locales_dir: Path, default_locale: str) -> None:
        self._default_locale = default_locale
        self._catalogs = self._load_catalogs(locales_dir)

    def resolve(self, requested: str | None) -> str:
        if requested and requested in self._catalogs:
            return requested
        return self._default_locale

    def for_locale(self, locale: str | None) -> Localizer:
        resolved = self.resolve(locale)
        return Localizer(resolved, self._catalogs[resolved])

    @staticmethod
    def _load_catalogs(locales_dir: Path) -> dict[str, dict[str, Any]]:
        catalogs: dict[str, dict[str, Any]] = {}
        for path in locales_dir.glob("*.json"):
            catalogs[path.stem] = json.loads(path.read_text(encoding="utf-8"))
        if not catalogs:
            raise FileNotFoundError(f"No locale files found in {locales_dir}")
        return catalogs
