import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
TIMEZONE = os.getenv("TIMEZONE", "Europe/Moscow")
DB_PATH = os.getenv("DB_PATH", "db.sqlite3")

if not BOT_TOKEN:
    raise RuntimeError(
        "BOT_TOKEN не задан. Создай файл .env (смотри .env.example) "
        "или задай переменную окружения BOT_TOKEN в Railway."
    )
