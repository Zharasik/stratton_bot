import calendar
from datetime import datetime, timedelta
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

MONTHS_RU = {1:"Январь",2:"Февраль",3:"Март",4:"Апрель",5:"Май",6:"Июнь",
             7:"Июль",8:"Август",9:"Сентябрь",10:"Октябрь",11:"Ноябрь",12:"Декабрь"}

NDA_FIELDS = [
    ("last_name","Фамилия"),("first_name","Имя"),("middle_name","Отчество"),
    ("iin","ИИН"),("doc_number","Номер документа"),("birth_date","Дата рождения"),
    ("issuing_authority","Орган выдачи"),("phone","Номер телефона"),("email","Email"),
    ("address","Адрес"),("nationality","Национальность"),("birth_place","Место рождения"),
    ("doc_expiry","Срок действия"),
]


def main_menu(has_testing: bool = False) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if has_testing:
        b.row(InlineKeyboardButton(text="📋 Подробная информация", callback_data="detailed_info_task"))
        b.row(InlineKeyboardButton(text="📅 Напомнить запись", callback_data="remind_testing"))
        b.row(InlineKeyboardButton(text="📹 Отправить тестирование", callback_data="submit_start"))
        b.row(InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_testing"))
    else:
        b.row(InlineKeyboardButton(text="📝 Записаться на тестирование", callback_data="signup_start"))
    b.row(InlineKeyboardButton(text="📊 Мой прогресс", callback_data="my_progress"))
    b.row(InlineKeyboardButton(text="❓ FAQ", callback_data="faq"))
    b.row(InlineKeyboardButton(text="ℹ️ О компании", callback_data="about_company"))
    b.row(InlineKeyboardButton(text="📞 Контакты", callback_data="contacts"))
    return b.as_markup()


def calendar_picker(year: int, month: int, days_ahead: int, slot_end_hour: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    today = datetime.now().date()
    max_date = today + timedelta(days=days_ahead)
    b.row(
        InlineKeyboardButton(text="◀️", callback_data=f"cal_prev:{year}:{month}"),
        InlineKeyboardButton(text=f"{MONTHS_RU[month]} {year}", callback_data="cal_ignore"),
        InlineKeyboardButton(text="▶️", callback_data=f"cal_next:{year}:{month}"),
    )
    b.row(*[InlineKeyboardButton(text=d, callback_data="cal_ignore") for d in ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"]])
    for week in calendar.monthcalendar(year, month):
        row = []
        for day_num in week:
            if day_num == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data="cal_ignore"))
                continue
            d = datetime(year, month, day_num).date()
            if d < today or d > max_date:
                row.append(InlineKeyboardButton(text="·", callback_data="cal_ignore"))
            elif d == today and datetime.now().hour + 1 >= slot_end_hour:
                row.append(InlineKeyboardButton(text="·", callback_data="cal_ignore"))
            elif d == today:
                row.append(InlineKeyboardButton(text=f"[{day_num}]", callback_data=f"pick_date:{d.strftime('%Y-%m-%d')}"))
            else:
                row.append(InlineKeyboardButton(text=str(day_num), callback_data=f"pick_date:{d.strftime('%Y-%m-%d')}"))
        b.row(*row)
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu"))
    return b.as_markup()


def time_slots(slots: list) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    buf = []
    for s in slots:
        hour = s.slot_start[:5] if hasattr(s, "slot_start") else s["slot_start"][:5]
        booked = s.booked_by if hasattr(s, "booked_by") else s.get("booked_by")
        slot_id = s.id if hasattr(s, "id") else s["id"]
        if booked is None:
            buf.append(InlineKeyboardButton(text=f"🟢 {hour}", callback_data=f"pick_slot:{slot_id}"))
        else:
            buf.append(InlineKeyboardButton(text=f"🔴 {hour}", callback_data="slot_busy"))
        if len(buf) == 4:
            b.row(*buf)
            buf = []
    if buf:
        b.row(*buf)
    b.row(InlineKeyboardButton(text="🔙 Календарь", callback_data="signup_start"))
    b.row(InlineKeyboardButton(text="🏠 Главная", callback_data="main_menu"))
    return b.as_markup()


def confirm_signup(slot_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_slot:{slot_id}"),
        InlineKeyboardButton(text="🔙 Назад", callback_data="signup_start"),
    )
    return b.as_markup()


def after_signup() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🏠 Главная", callback_data="main_menu"))
    b.row(InlineKeyboardButton(text="📋 Подробная информация", callback_data="detailed_info_task"))
    b.row(InlineKeyboardButton(text="📅 Напомнить", callback_data="remind_testing"))
    b.row(InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_testing"))
    return b.as_markup()


def confirm_cancel() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✅ Да", callback_data="confirm_cancel"),
        InlineKeyboardButton(text="❌ Нет", callback_data="main_menu"),
    )
    return b.as_markup()


def nda_fields(data: dict) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for key, label in NDA_FIELDS:
        value = data.get(key, "")
        icon = "✅" if value else "❌"
        text = f"{icon} {label}: {value or 'Не заполнено'}"
        if len(text) > 50:
            text = text[:47] + "..."
        b.row(InlineKeyboardButton(text=text, callback_data=f"nda_edit:{key}"))
    b.row(InlineKeyboardButton(text="✅ Подтвердить", callback_data="nda_confirm"))
    return b.as_markup()


def nda_back_to_fields() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔙 К полям", callback_data="nda_show_fields"))
    return b.as_markup()


def faq_menu() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    items = [("📝 Запись","faq:запись"),("📋 Задание","faq:задание"),("📹 Видео","faq:видео"),
             ("❌ Отмена","faq:отмена"),("⏳ Результат","faq:результат"),("📄 NDA","faq:nda"),
             ("🔗 GitHub","faq:github"),("🔄 Повтор","faq:повтор")]
    for text, cb in items:
        b.row(InlineKeyboardButton(text=text, callback_data=cb))
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu"))
    return b.as_markup()


def admin_menu() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    items = [("📊 Статистика","admin_stats"),("👥 Пользователи","admin_users"),
             ("📝 Записи","admin_testings"),("📩 Работы","admin_submissions"),
             ("🔍 Поиск NDA","admin_nda_search"),("📤 Экспорт CSV","admin_export"),
             ("📢 Рассылка","admin_broadcast"),("🔙 Выход","main_menu")]
    for text, cb in items:
        b.row(InlineKeyboardButton(text=text, callback_data=cb))
    return b.as_markup()


def admin_review(sub_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(
        InlineKeyboardButton(text="✅ Принять", callback_data=f"review_accept:{sub_id}"),
        InlineKeyboardButton(text="❌ Отклонить", callback_data=f"review_reject:{sub_id}"),
    )
    return b.as_markup()


def back_to_main() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu"))
    return b.as_markup()
