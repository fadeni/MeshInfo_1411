# bot/database.py

import sqlite3
from config.settings import DATABASE_PATH

def init_db():
    conn = sqlite3.connect(DATABASE_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            telegram_user_id INTEGER PRIMARY KEY,
            encrypted_token BLOB
        )
    ''')
    conn.commit()
    conn.close()

def get_db_connection():
    return sqlite3.connect(DATABASE_PATH)

def delete_user_data(telegram_user_id: int):
    """
    Удаляет данные пользователя (зашифрованный токен) из базы данных.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('DELETE FROM users WHERE telegram_user_id = ?', (telegram_user_id,))
    conn.commit()
    conn.close()
