from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from stratton_bot.infrastructure.i18n.translator import Localizer


def main_menu(localizer: Localizer, has_testing: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    if has_testing:
        builder.row(
            InlineKeyboardButton(
                text=localizer.text("buttons.testing.details"),
                callback_data="detailed_info_task",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=localizer.text("buttons.testing.remind"),
                callback_data="remind_testing",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=localizer.text("buttons.testing.submit"),
                callback_data="submit_start",
            )
        )
        builder.row(
            InlineKeyboardButton(
                text=localizer.text("buttons.testing.cancel"),
                callback_data="cancel_testing",
            )
        )
    else:
        builder.row(
            InlineKeyboardButton(
                text=localizer.text("buttons.testing.signup"),
                callback_data="signup_start",
            )
        )
    builder.row(InlineKeyboardButton(text=localizer.text("buttons.menu.progress"), callback_data="my_progress"))
    builder.row(InlineKeyboardButton(text=localizer.text("buttons.menu.faq"), callback_data="faq"))
    builder.row(InlineKeyboardButton(text=localizer.text("buttons.menu.company"), callback_data="about_company"))
    builder.row(InlineKeyboardButton(text=localizer.text("buttons.menu.contacts"), callback_data="contacts"))
    return builder.as_markup()


def back_to_main(localizer: Localizer) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=localizer.text("buttons.common.back"), callback_data="main_menu"))
    return builder.as_markup()


def faq_menu(localizer: Localizer) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    items = [
        ("faq.signup", "faq:signup"),
        ("faq.task", "faq:task"),
        ("faq.video", "faq:video"),
        ("faq.cancel", "faq:cancel"),
        ("faq.result", "faq:result"),
        ("faq.nda", "faq:nda"),
        ("faq.github", "faq:github"),
        ("faq.retry", "faq:retry"),
    ]
    for key, callback_data in items:
        builder.row(InlineKeyboardButton(text=localizer.text(f"buttons.{key}"), callback_data=callback_data))
    builder.row(InlineKeyboardButton(text=localizer.text("buttons.common.back"), callback_data="main_menu"))
    return builder.as_markup()
