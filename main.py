# main.py

import logging
from telegram.ext import ApplicationBuilder
from config.settings import TELEGRAM_TOKEN, LOGGING_LEVEL
from bot.handlers import setup_handlers
from bot.database import init_db

def main():
    # Инициализируем логирование
    logging.basicConfig(level=LOGGING_LEVEL)
    logger = logging.getLogger(__name__)

    # Инициализируем базу данных (создаёт таблицу, если ещё нет)
    init_db()

    # Создаем приложение Telegram
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    # Установка обработчиков
    setup_handlers(application)

    # Запуск бота
    application.run_polling()

if __name__ == '__main__':
    main()
