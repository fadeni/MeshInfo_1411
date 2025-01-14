# bot/handlers.py
import re
import logging
import json
from datetime import datetime, date

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Update,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    CommandHandler,
    CallbackQueryHandler,
    ConversationHandler,
    MessageHandler,
    filters,
    ContextTypes,
)
from .auth import (
    is_user_logged_in,
    get_api_client,
    save_token_db,
    load_token_db,
    encrypt_token,
    decrypt_token,
)
from .utils import generate_calendar_keyboard
from .database import delete_user_data
from octodiary.apis import AsyncMobileAPI
from octodiary.urls import Systems
from octodiary.types.enter_sms_code import EnterSmsCode

logger = logging.getLogger(__name__)

# Состояния для ConversationHandler
USERNAME, PASSWORD, SMS_CODE = range(3)

def setup_handlers(application):
    # Создаем ConversationHandler для логина
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('login', login)],
        states={
            USERNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_username)],
            PASSWORD: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_password)],
            SMS_CODE: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_sms_code)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    application.add_handler(CommandHandler('start', start))
    application.add_handler(conv_handler)
    application.add_handler(CommandHandler('schedule', schedule))
    application.add_handler(CallbackQueryHandler(handle_callback_query))

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    telegram_user_id = user.id

    if await is_user_logged_in(telegram_user_id):
        # Если авторизован
        keyboard = [
            [InlineKeyboardButton("Посмотреть расписание", callback_data='view_schedule')],
            [InlineKeyboardButton("Удалить мои данные из бота", callback_data='delete_my_data')],
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f'Здравствуйте, {user.first_name}! Вы уже авторизованы. Выберите действие:',
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text(
            f'Здравствуйте, {user.first_name}! Чтобы начать, введите команду /login.'
        )

async def login(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_user_id = update.effective_user.id
    if await is_user_logged_in(telegram_user_id):
        await update.message.reply_text('Вы уже авторизованы.')
        return ConversationHandler.END
    else:
        await update.message.reply_text('Пожалуйста, введите ваш логин:')
        return USERNAME

async def get_username(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['username'] = update.message.text
    await update.message.reply_text('Теперь введите ваш пароль:')
    return PASSWORD

async def get_password(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data['password'] = update.message.text
    await update.message.reply_text('Пожалуйста, подождите, идёт авторизация...')

    telegram_user_id = update.effective_user.id
    username = context.user_data['username']
    password = context.user_data['password']
    api, sms_code_obj = await get_api_client(telegram_user_id, username, password)

    if api is None:
        await update.message.reply_text('Ошибка авторизации. Попробуйте снова с помощью команды /login.')
        return ConversationHandler.END

    context.user_data['api'] = api
    context.user_data['sms_code_obj'] = sms_code_obj

    if sms_code_obj:
        await update.message.reply_text('Введите код из SMS:')
        return SMS_CODE
    else:
        await update.message.reply_text('Авторизация успешна! Теперь вы можете получить расписание с помощью команды /schedule.')
        return ConversationHandler.END

async def get_sms_code(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sms_code = update.message.text
    telegram_user_id = update.effective_user.id
    api = context.user_data['api']
    sms_code_obj = context.user_data['sms_code_obj']

    try:
        api.token = await sms_code_obj.async_enter_code(sms_code)
        encrypted_token = encrypt_token(api.token)
        save_token_db(telegram_user_id, encrypted_token)
    except Exception as e:
        logger.error("Ошибка при вводе SMS-кода для пользователя %s: %s", telegram_user_id, e)
        await update.message.reply_text('Неверный SMS-код. Попробуйте снова с помощью команды /login.')
        return ConversationHandler.END

    await update.message.reply_text('Авторизация успешна! Теперь вы можете получить расписание с помощью команды /schedule.')
    return ConversationHandler.END

async def schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    telegram_user_id = update.effective_user.id
    api = context.user_data.get('api')

    if not api:
        encrypted_token = load_token_db(telegram_user_id)
        if encrypted_token:
            try:
                token_data = decrypt_token(encrypted_token)
                api = AsyncMobileAPI(system=Systems.MES)
                api.token = token_data
                context.user_data['api'] = api
            except Exception as e:
                logger.error("Ошибка при дешифровании токена для пользователя %s: %s", telegram_user_id, e)
                await update.effective_message.reply_text('Сессия истекла. Пожалуйста, выполните /login снова.')
                return
        else:
            await update.effective_message.reply_text('Пожалуйста, выполните вход с помощью команды /login.')
            return

    # Отображаем календарь
    reply_markup = generate_calendar_keyboard()
    await update.effective_message.reply_text('Выберите дату:', reply_markup=reply_markup)

async def select_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    selected_date_str = query.data

    if selected_date_str.startswith('calendar_'):
        # Переключение месяца
        _, year, month = selected_date_str.split('_')
        year = int(year)
        month = int(month)
        reply_markup = generate_calendar_keyboard(year, month)
        await query.edit_message_reply_markup(reply_markup)
        return

    if selected_date_str == 'ignore':
        return

    selected_date = datetime.strptime(selected_date_str, '%Y-%m-%d').date()
    telegram_user_id = update.effective_user.id
    api = context.user_data.get('api')

    if not api:
        await query.edit_message_text('Сессия истекла. Пожалуйста, выполните /login снова.')
        return

    try:
        profiles = await api.get_users_profile_info()
        profile_id = profiles[0].id

        profile = await api.get_family_profile(profile_id=profile_id)
        mes_role = profile.profile.type

        child = profile.children[0]
        person_guid = child.contingent_guid
        student_id = child.id

        if not person_guid or not student_id:
            await query.edit_message_text("Не удалось получить идентификаторы ученика.")
            return

        context.user_data['person_guid'] = person_guid
        context.user_data['mes_role'] = mes_role

        events_response = await api.get_events(
            person_id=person_guid,
            mes_role=mes_role,
            begin_date=selected_date,
            end_date=selected_date,
        )
    except Exception as e:
        logger.error("Ошибка при получении расписания для пользователя %s: %s", telegram_user_id, e)
        await query.edit_message_text('Ошибка при получении расписания. Пожалуйста, попробуйте позже.')
        return

    if not events_response.response:
        await query.edit_message_text('Расписание не найдено на выбранную дату.')
        return

    # Фильтруем уроки без информации
    lessons = [
        event for event in events_response.response
        if event.subject_name and event.start_at and event.finish_at
    ]

    if not lessons:
        await query.edit_message_text('На выбранную дату нет уроков.')
        return

    keyboard = []
    for idx, event in enumerate(lessons):
        start_time = event.start_at.strftime('%H:%M')
        end_time = event.finish_at.strftime('%H:%M')
        subject = event.subject_name
        button_text = f'{start_time}-{end_time} {subject}'
        callback_data = f'lesson_{idx}'
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    keyboard.append([InlineKeyboardButton("Вернуться к расписанию", callback_data='back_to_schedule')])
    context.user_data['lessons'] = lessons
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text(f'Выберите урок на {selected_date.strftime("%d.%m.%Y")}:', reply_markup=reply_markup)

async def lesson_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    callback_data = query.data

    if not callback_data.startswith('lesson_'):
        return

    lesson_index = int(callback_data.split('_')[1])
    lessons = context.user_data.get('lessons')

    if lessons is None or lesson_index >= len(lessons):
        await query.edit_message_text('Ошибка: урок не найден.')
        return

    event = lessons[lesson_index]

    start_time = event.start_at.strftime('%H:%M') if event.start_at else 'Не указано'
    end_time = event.finish_at.strftime('%H:%M') if event.finish_at else 'Не указано'
    subject = event.subject_name or 'Не указано'
    room = event.room_number or 'Не указан'
    theme = event.lesson_theme or 'Не указана'

    homework_descriptions = []
    if event.homework and event.homework.descriptions:
        homework_descriptions = event.homework.descriptions

    has_cdz = bool(event.materials)

    message = f'⏰ {start_time}-{end_time}\n'
    message += f'📚 Предмет: {subject}\n'
    message += f'🚪 Кабинет: {room}\n'
    message += f'📖 Тема урока: {theme}\n'

    if homework_descriptions:
        message += '📝 Домашнее задание:\n'
        for desc in homework_descriptions:
            message += f'- {desc}\n'
    else:
        message += '📝 Домашнее задание: нет\n'

    if has_cdz:
        message += '💻 Учитель прикрепил ЦДЗ к ДЗ.\n'

    keyboard = [
        [InlineKeyboardButton("Вернуться к урокам", callback_data='back_to_lessons')],
        [InlineKeyboardButton("Вернуться к расписанию", callback_data='back_to_schedule')]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await query.edit_message_text(message, reply_markup=reply_markup)

async def back_to_lessons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    lessons = context.user_data.get('lessons')
    if lessons is None:
        await query.edit_message_text('Ошибка: список уроков не найден.')
        return

    keyboard = []
    for idx, event in enumerate(lessons):
        start_time = event.start_at.strftime('%H:%M')
        end_time = event.finish_at.strftime('%H:%M')
        subject = event.subject_name
        button_text = f'{start_time}-{end_time} {subject}'
        callback_data = f'lesson_{idx}'
        keyboard.append([InlineKeyboardButton(button_text, callback_data=callback_data)])

    keyboard.append([InlineKeyboardButton("Вернуться к расписанию", callback_data='back_to_schedule')])
    reply_markup = InlineKeyboardMarkup(keyboard)
    await query.edit_message_text('Выберите урок:', reply_markup=reply_markup)

async def back_to_schedule(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    reply_markup = generate_calendar_keyboard()
    await query.edit_message_text('Выберите дату:', reply_markup=reply_markup)

async def delete_my_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    telegram_user_id = update.effective_user.id
    delete_user_data(telegram_user_id)
    context.user_data.clear()

    await query.edit_message_text('Ваши данные были удалены из бота. Чтобы начать заново, используйте /start.')

import re

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    data = query.data

    print("callback_data:", data)  # Временно для отладки

    if data == 'back_to_schedule':
        await back_to_schedule(update, context)
    elif data == 'back_to_lessons':
        await back_to_lessons(update, context)
    elif data == 'delete_my_data':
        await delete_my_data(update, context)
    elif data == 'view_schedule':
        await schedule(update, context)
    elif data.startswith('lesson_'):
        await lesson_detail(update, context)
    elif data.startswith('calendar_') or data == 'ignore':
        # Переключение месяцев или ничего не делаем для ignore
        await select_date(update, context)
    elif re.match(r'^\d{4}-\d{2}-\d{2}$', data):
        # Если дата в формате YYYY-MM-DD -> вызываем select_date
        await select_date(update, context)
    else:
        # На всякий случай отладочная ветка
        print("Неизвестный callback_data:", data)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Прерывает диалоговое состояние (ConversationHandler).
    """
    await update.message.reply_text(
        "Операция отменена. Если нужно начать сначала, введите /start."
    )
    return ConversationHandler.END
