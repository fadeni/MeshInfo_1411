# config/settings.py

import os

# Замените на реальный токен вашего Telegram-бота
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '7900995488:AAHP-vD0DMqeSQBIvdemyJhKp53xoooag74')

# Уровень логирования: DEBUG, INFO, WARNING, ERROR, CRITICAL
LOGGING_LEVEL = os.getenv('LOGGING_LEVEL', 'INFO')

# Путь к файлу базы данных
DATABASE_PATH = 'users.db'

# Путь к файлу ключа шифрования для Fernet
ENCRYPTION_KEY_PATH = 'encryption.key'
