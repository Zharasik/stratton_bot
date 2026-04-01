import calendar
from datetime import datetime, timedelta
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from config import DAYS_AHEAD, SLOT_START_HOUR, SLOT_END_HOUR

MONTHS_RU_FULL = {1:"Январь",2:"Февраль",3:"Март",4:"Апрель",5:"Май",6:"Июнь",7:"Июль",8:"Август",9:"Сентябрь",10:"Октябрь",11:"Ноябрь",12:"Декабрь"}

def main_menu_kb(has_testing: bool = False) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    if not has_testing:
        b.row(InlineKeyboardButton(text="📝 Записаться на тестирование", callback_data="signup_start"))
    else:
        b.row(InlineKeyboardButton(text="📋 Подробная информация", callback_data="detailed_info_task"))
        b.row(InlineKeyboardButton(text="📅 Напомнить запись", callback_data="remind_testing"))
        b.row(InlineKeyboardButton(text="📹 Отправить тестирование", callback_data="submit_start"))
        b.row(InlineKeyboardButton(text="❌ Отменить тестирование", callback_data="cancel_testing"))
    b.row(InlineKeyboardButton(text="📊 Мой прогресс", callback_data="my_progress"))
    b.row(InlineKeyboardButton(text="❓ FAQ", callback_data="faq"))
    b.row(InlineKeyboardButton(text="ℹ️ О компании", callback_data="about_company"))
    b.row(InlineKeyboardButton(text="📞 Контакты", callback_data="contacts"))
    return b.as_markup()

def calendar_kb(year: int, month: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    today = datetime.now().date()
    max_date = today + timedelta(days=DAYS_AHEAD)
    b.row(InlineKeyboardButton(text="◀️", callback_data=f"cal_prev:{year}:{month}"),
          InlineKeyboardButton(text=f"{MONTHS_RU_FULL[month]} {year}", callback_data="cal_ignore"),
          InlineKeyboardButton(text="▶️", callback_data=f"cal_next:{year}:{month}"))
    b.row(*[InlineKeyboardButton(text=d, callback_data="cal_ignore") for d in ["Пн","Вт","Ср","Чт","Пт","Сб","Вс"]])
    for week in calendar.monthcalendar(year, month):
        row = []
        for day_num in week:
            if day_num == 0:
                row.append(InlineKeyboardButton(text=" ", callback_data="cal_ignore"))
            else:
                d = datetime(year, month, day_num).date()
                if d < today or d > max_date:
                    row.append(InlineKeyboardButton(text="·", callback_data="cal_ignore"))
                elif d == today:
                    if datetime.now().hour + 1 >= SLOT_END_HOUR:
                        row.append(InlineKeyboardButton(text="·", callback_data="cal_ignore"))
                    else:
                        row.append(InlineKeyboardButton(text=f"[{day_num}]", callback_data=f"pick_date:{d.strftime('%Y-%m-%d')}"))
                else:
                    row.append(InlineKeyboardButton(text=str(day_num), callback_data=f"pick_date:{d.strftime('%Y-%m-%d')}"))
        b.row(*row)
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu"))
    return b.as_markup()

def time_slots_kb(all_slots: list, date_str: str) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    has_free = False
    buf = []
    for s in all_slots:
        h = s["slot_start"][:5]
        if s["booked_by"] is None:
            buf.append(InlineKeyboardButton(text=f"🟢 {h}", callback_data=f"pick_slot:{s['id']}"))
            has_free = True
        else:
            buf.append(InlineKeyboardButton(text=f"🔴 {h}", callback_data="slot_busy"))
        if len(buf) == 4:
            b.row(*buf); buf = []
    if buf: b.row(*buf)
    if not has_free:
        b.row(InlineKeyboardButton(text="😔 Все заняты", callback_data="slot_busy"))
    b.row(InlineKeyboardButton(text="🔙 Календарь", callback_data="signup_start"))
    b.row(InlineKeyboardButton(text="🏠 Главная", callback_data="main_menu"))
    return b.as_markup()

def confirm_signup_kb(slot_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✅ Подтвердить", callback_data=f"confirm_slot:{slot_id}"),
          InlineKeyboardButton(text="🔙 Назад", callback_data="signup_start"))
    return b.as_markup()

def after_signup_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🏠 Главная", callback_data="main_menu"))
    b.row(InlineKeyboardButton(text="📋 Подробная информация", callback_data="detailed_info_task"))
    b.row(InlineKeyboardButton(text="📞 Контакты", callback_data="contacts"))
    b.row(InlineKeyboardButton(text="❌ Отменить", callback_data="cancel_testing"))
    b.row(InlineKeyboardButton(text="📅 Напомнить", callback_data="remind_testing"))
    return b.as_markup()

def confirm_cancel_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✅ Да", callback_data="confirm_cancel"),
          InlineKeyboardButton(text="❌ Нет", callback_data="main_menu"))
    return b.as_markup()

NDA_FIELDS = [("last_name","Фамилия"),("first_name","Имя"),("middle_name","Отчество"),("iin","ИИН"),("doc_number","Номер документа"),("birth_date","Дата рождения"),("issuing_authority","Орган выдачи"),("phone","Номер телефона"),("email","Email"),("address","Адрес проживания"),("nationality","Национальность"),("birth_place","Место рождения"),("doc_expiry","Срок действия")]

def nda_fields_kb(data: dict) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    for fk, fl in NDA_FIELDS:
        v = data.get(fk, "")
        d = f"{'✅' if v else '❌'} {fl}: {v or 'Не заполнено'}"
        if len(d) > 50: d = d[:47] + "..."
        b.row(InlineKeyboardButton(text=d, callback_data=f"nda_edit:{fk}"))
    b.row(InlineKeyboardButton(text="✅ Подтвердить", callback_data="nda_confirm"))
    return b.as_markup()

def nda_cancel_edit_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔙 К полям", callback_data="nda_show_fields"))
    return b.as_markup()

def faq_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📝 Запись", callback_data="faq:запись"))
    b.row(InlineKeyboardButton(text="📋 Задание", callback_data="faq:задание"))
    b.row(InlineKeyboardButton(text="📹 Видео", callback_data="faq:видео"))
    b.row(InlineKeyboardButton(text="❌ Отмена", callback_data="faq:отмена"))
    b.row(InlineKeyboardButton(text="⏳ Результат", callback_data="faq:результат"))
    b.row(InlineKeyboardButton(text="📄 NDA", callback_data="faq:nda"))
    b.row(InlineKeyboardButton(text="🔗 GitHub", callback_data="faq:github"))
    b.row(InlineKeyboardButton(text="🔄 Повтор", callback_data="faq:повтор"))
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu"))
    return b.as_markup()

def admin_menu_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats"))
    b.row(InlineKeyboardButton(text="👥 Пользователи", callback_data="admin_users"))
    b.row(InlineKeyboardButton(text="📝 Записи", callback_data="admin_testings"))
    b.row(InlineKeyboardButton(text="📩 Работы", callback_data="admin_submissions"))
    b.row(InlineKeyboardButton(text="🔍 Поиск NDA", callback_data="admin_nda_search"))
    b.row(InlineKeyboardButton(text="📤 Экспорт CSV", callback_data="admin_export"))
    b.row(InlineKeyboardButton(text="📢 Рассылка", callback_data="admin_broadcast"))
    b.row(InlineKeyboardButton(text="🔙 Выход", callback_data="main_menu"))
    return b.as_markup()

def admin_review_kb(sub_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="✅ Принять", callback_data=f"review_accept:{sub_id}"),
          InlineKeyboardButton(text="❌ Отклонить", callback_data=f"review_reject:{sub_id}"))
    return b.as_markup()

def admin_user_detail_kb(user_id: int) -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔍 NDA", callback_data=f"admin_user_nda:{user_id}"))
    b.row(InlineKeyboardButton(text="🔙 Список", callback_data="admin_users"))
    return b.as_markup()

def back_to_main_kb() -> InlineKeyboardMarkup:
    b = InlineKeyboardBuilder()
    b.row(InlineKeyboardButton(text="🔙 Назад", callback_data="main_menu"))
    return b.as_markup()
