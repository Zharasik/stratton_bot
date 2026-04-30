from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram.utils.keyboard import InlineKeyboardBuilder

from stratton_bot.infrastructure.i18n.translator import Localizer


def admin_menu(localizer: Localizer, web_app_url: str = "") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    items = [
        ("buttons.admin.stats", "admin_stats"),
        ("buttons.admin.users", "admin_users"),
        ("buttons.admin.testings", "admin_testings"),
        ("buttons.admin.submissions", "admin_submissions"),
        ("buttons.admin.nda_search", "admin_nda_search"),
        ("buttons.admin.export", "admin_export"),
        ("buttons.admin.broadcast", "admin_broadcast"),
        ("buttons.admin.exit", "main_menu"),
    ]
    for key, callback_data in items:
        builder.row(InlineKeyboardButton(text=localizer.text(key), callback_data=callback_data))

    if web_app_url:
        if web_app_url.startswith("https://"):
            btn = InlineKeyboardButton(
                text=localizer.text("buttons.admin.nda_webapp"),
                web_app=WebAppInfo(url=web_app_url),
            )
        else:
            btn = InlineKeyboardButton(
                text=localizer.text("buttons.admin.nda_webapp"),
                url=web_app_url,
            )
        builder.row(btn)

    return builder.as_markup()


def admin_review(localizer: Localizer, submission_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text=localizer.text("buttons.admin.accept"),
            callback_data=f"review_accept:{submission_id}",
        ),
        InlineKeyboardButton(
            text=localizer.text("buttons.admin.reject"),
            callback_data=f"review_reject:{submission_id}",
        ),
    )
    return builder.as_markup()
