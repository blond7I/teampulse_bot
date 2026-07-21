from typing import List

# Welcome and instructions
START_MESSAGE = """
Привет! Я бот для async-стендапов команды.

Команды:
- /start в группе — зарегистрировать команду
- /join <chat_id> в личке — присоединиться к команде
- /settime HH:MM HH:MM — установить время опроса и дайджеста (для админов)
- /history — последние стендапы
- /members — список участников
- /pause /resume — пауза/возобновление
- /testsurvey — тестовый опрос
- /testdigest — тестовый дайджест
"""

JOIN_SUCCESS = "Вы присоединились к команде {team_name}!"
ALREADY_JOINED = "Вы уже в команде."
TEAM_NOT_FOUND = "Команда не найдена."
NOT_ADMIN = "Только администраторы могут использовать эту команду."
NO_TEAM = "Сначала зарегистрируйте команду в группе с помощью /start."

# Survey questions
QUESTION_YESTERDAY = "Что делал(а) вчера?"
QUESTION_TODAY = "Что планируешь сегодня?"
QUESTION_BLOCKERS = "Есть блокеры? (если нет — напиши 'нет')"

SURVEY_COMPLETE = "Спасибо! Твой стендап сохранён. 🔥"

# Reminders
REMINDER_MESSAGES = [
    "{name}, не забудь поделиться своим стендапом! ⏰",
    "{name}, время для стендапа! Что было вчера? 🚀",
    "{name}, ждём твой отчет за день! 🌟",
    "Эй {name}, стендап ждёт! Не пропусти 🔥",
    "{name}, расскажи, что планируешь сегодня? 😉"
]

# Digest
DIGEST_HEADER = "📊 Дайджест TeamPulse — {date}"
MEMBER_LINE = "👤 {name} (🔥 {streak} дней подряд)\nВчера: {yesterday}\nСегодня: {today}\nБлокеры: {blockers}\n"
NO_RESPONSE = "⚠️ не ответил(а)"
DIGEST_FOOTER = "\n—\nОтветили: {answered}/{total}"

MEMBERS_LIST = "Участники команды:\n{members}"
PAUSE_SUCCESS = "Бот приостановлен для команды."
RESUME_SUCCESS = "Бот возобновлён для команды."
HISTORY_EMPTY = "Нет предыдущих стендапов."
