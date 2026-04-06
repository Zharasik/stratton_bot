from __future__ import annotations

import calendar
from datetime import datetime, timedelta

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from stratton_bot.domain.entities import TimeSlot
from stratton_bot.infrastructure.i18n.translator import Localizer
from stratton_bot.presentation.constants import NDA_FIELD_KEYS


def calendar_picker(
    localizer: Localizer,
    year: int,
    month: int,
    *,
    days_ahead: int,
    slot_end_hour: int,
) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    today = datetime.now().date()
    max_date = today + timedelta(days=days_ahead)
    months = localizer.mapping("calendar.months")
    weekdays = localizer.mapping("calendar.weekdays")

    builder.row(
        InlineKeyboardButton(text="◀", callback_data=f"cal_prev:{year}:{month}"),
        InlineKeyboardButton(text=f"{months[str(month)]} {year}", callback_data="cal_ignore"),
        InlineKeyboardButton(text="▶", callback_data=f"cal_next:{year}:{month}"),
    )
    builder.row(*[InlineKeyboardButton(text=day, callback_data="cal_ignore") for day in weekdays.values()])

    for week in calendar.monthcalendar(year, month):
        row = []
        for day_number in week:
            if day_number == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data="cal_ignore"))
                continue
            current_date = datetime(year, month, day_number).date()
            if current_date < today or current_date > max_date:
                row.append(InlineKeyboardButton(text="·", callback_data="cal_ignore"))
            elif current_date == today and datetime.now().hour + 1 >= slot_end_hour:
                row.append(InlineKeyboardButton(text="·", callback_data="cal_ignore"))
            elif current_date == today:
                row.append(
                    InlineKeyboardButton(
                        text=f"[{day_number}]",
                        callback_data=f"pick_date:{current_date:%Y-%m-%d}",
                    )
                )
            else:
                row.append(
                    InlineKeyboardButton(
                        text=str(day_number),
                        callback_data=f"pick_date:{current_date:%Y-%m-%d}",
                    )
                )
        builder.row(*row)
    builder.row(InlineKeyboardButton(text=localizer.text("buttons.common.back"), callback_data="main_menu"))
    return builder.as_markup()


def time_slots(localizer: Localizer, slots: list[TimeSlot]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    row: list[InlineKeyboardButton] = []
    for slot in slots:
        label = f"🟢 {slot.slot_start[:5]}" if slot.booked_by is None else f"🔴 {slot.slot_start[:5]}"
        callback_data = f"pick_slot:{slot.id}" if slot.booked_by is None else "slot_busy"
        row.append(InlineKeyboardButton(text=label, callback_data=callback_data))
        if len(row) == 4:
            builder.row(*row)
            row = []
    if row:
        builder.row(*row)
    builder.row(InlineKeyboardButton(text=localizer.text("buttons.testing.calendar"), callback_data="signup_start"))
    builder.row(InlineKeyboardButton(text=localizer.text("buttons.common.home"), callback_data="main_menu"))
    return builder.as_markup()


def confirm_signup(localizer: Localizer, slot_id: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=localizer.text("buttons.common.confirm"), callback_data=f"confirm_slot:{slot_id}"),
        InlineKeyboardButton(text=localizer.text("buttons.common.back"), callback_data="signup_start"),
    )
    return builder.as_markup()


def after_signup(localizer: Localizer) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=localizer.text("buttons.common.home"), callback_data="main_menu"))
    builder.row(InlineKeyboardButton(text=localizer.text("buttons.testing.details"), callback_data="detailed_info_task"))
    builder.row(InlineKeyboardButton(text=localizer.text("buttons.testing.remind_short"), callback_data="remind_testing"))
    builder.row(InlineKeyboardButton(text=localizer.text("buttons.testing.cancel"), callback_data="cancel_testing"))
    return builder.as_markup()


def confirm_cancel(localizer: Localizer) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text=localizer.text("buttons.common.yes"), callback_data="confirm_cancel"),
        InlineKeyboardButton(text=localizer.text("buttons.common.no"), callback_data="main_menu"),
    )
    return builder.as_markup()


def nda_fields(localizer: Localizer, data: dict[str, str | None]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for field_key, label_key in NDA_FIELD_KEYS:
        value = data.get(field_key, "")
        icon = "✅" if value else "❌"
        label = localizer.text(label_key)
        text = f"{icon} {label}: {value or localizer.text('nda.not_filled')}"
        builder.row(InlineKeyboardButton(text=text[:60], callback_data=f"nda_edit:{field_key}"))
    builder.row(InlineKeyboardButton(text=localizer.text("buttons.common.confirm"), callback_data="nda_confirm"))
    return builder.as_markup()


def nda_back_to_fields(localizer: Localizer) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text=localizer.text("buttons.nda.to_fields"), callback_data="nda_show_fields"))
    return builder.as_markup()
