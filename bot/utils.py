# bot/utils.py

import calendar
from datetime import date
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def generate_calendar_keyboard(year=None, month=None):
    """
    Генерирует инлайн-календарь с переключением месяцев.
    Кнопки дней вызывают callback_data='YYYY-MM-DD'.
    """
    if year is None and month is None:
        today = date.today()
        year = today.year
        month = today.month

    keyboard = []

    # Название месяца и года
    month_name = calendar.month_name[month]
    header = [InlineKeyboardButton(f'{month_name} {year}', callback_data='ignore')]
    keyboard.append(header)

    # Дни недели
    week_days = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс']
    keyboard.append([InlineKeyboardButton(day, callback_data='ignore') for day in week_days])

    # Заполняем даты месяца
    month_calendar = calendar.monthcalendar(year, month)
    for week in month_calendar:
        row = []
        for day_ in week:
            if day_ == 0:
                # Нет даты (пустая ячейка)
                row.append(InlineKeyboardButton(' ', callback_data='ignore'))
            else:
                button_date = date(year, month, day_)
                callback_data = button_date.strftime('%Y-%m-%d')
                row.append(InlineKeyboardButton(str(day_), callback_data=callback_data))
        keyboard.append(row)

    # Навигация << >>
    prev_month = month - 1 if month > 1 else 12
    prev_year = year - 1 if month == 1 else year
    next_month = month + 1 if month < 12 else 1
    next_year = year + 1 if month == 12 else year

    nav_row = [
        InlineKeyboardButton('<<', callback_data=f'calendar_{prev_year}_{prev_month}'),
        InlineKeyboardButton(' ', callback_data='ignore'),
        InlineKeyboardButton('>>', callback_data=f'calendar_{next_year}_{next_month}')
    ]
    keyboard.append(nav_row)

    return InlineKeyboardMarkup(keyboard)
