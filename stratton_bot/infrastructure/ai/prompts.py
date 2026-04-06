from __future__ import annotations

from stratton_bot.domain.exceptions import NotFoundError


class DictPromptBuilder:
    def __init__(self) -> None:
        self._templates = {
            "id_card_front": (
                'Извлеки с фото казахстанского удостоверения личности JSON-объектом вида '
                '{"last_name":"","first_name":"","middle_name":"","iin":"","doc_number":"","birth_date":"ДД.ММ.ГГГГ"}. '
                "Если поле не видно, верни пустую строку. Ответ только JSON."
            ),
            "id_card_back": (
                'Извлеки с фото оборотной стороны удостоверения личности JSON-объектом вида '
                '{"issuing_authority":"","nationality":"","birth_place":"","doc_expiry":"ДД.ММ.ГГГГ","doc_number":""}. '
                "Если поле не видно, верни пустую строку. Ответ только JSON."
            ),
        }

    def build(self, template_name: str) -> str:
        try:
            return self._templates[template_name]
        except KeyError as error:
            raise NotFoundError(f"Prompt template '{template_name}' not found") from error
