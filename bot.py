import asyncio
import logging
import random
from datetime import datetime, timedelta
import pytz

from aiogram import Bot, Dispatcher, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.base import StorageKey
from aiogram.types import Message
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import BOT_TOKEN, TIMEZONE, DB_PATH
from database import *
from messages import *

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
dp = Dispatcher()
router = Router()
dp.include_router(router)

TZ = pytz.timezone(TIMEZONE)


class SurveyStates(StatesGroup):
    waiting_yesterday = State()
    waiting_today = State()
    waiting_blockers = State()


scheduler = AsyncIOScheduler(timezone=TIMEZONE)


def now_tz() -> datetime:
    return datetime.now(TZ)


def today_str() -> str:
    return now_tz().strftime("%Y-%m-%d")


def add_minutes_to_hhmm(hhmm: str, minutes: int) -> str:
    """'10:00' + 30 -> '10:30'. Wraps past midnight if needed."""
    h, m = map(int, hhmm.split(":"))
    total = h * 60 + m + minutes
    total %= 24 * 60
    return f"{total // 60:02d}:{total % 60:02d}"


async def is_admin(chat_id: int, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in ['administrator', 'creator']
    except Exception:
        return False


# ---------- FSM helper: this is the core fix ----------
# Ранее вопрос отправлялся через bot.send_message() без установки состояния FSM,
# поэтому ответ участника ("вчера доделал бэкенд") никогда не попадал ни в один
# хендлер SurveyStates и не сохранялся. Здесь состояние выставляется явно через
# StorageKey для конкретного user_id — это и заставляет FSM реально работать.
async def start_survey_for_member(member: Dict) -> bool:
    key = StorageKey(bot_id=bot.id, chat_id=member['user_id'], user_id=member['user_id'])
    state = FSMContext(storage=dp.storage, key=key)
    try:
        await bot.send_message(member['user_id'], QUESTION_YESTERDAY)
    except Exception as e:
        logger.warning(f"Не удалось написать участнику {member['user_id']}: {e}")
        return False
    await state.set_state(SurveyStates.waiting_yesterday)
    await state.update_data(member_id=member['id'], team_id=member['team_id'])
    return True


@router.message(Command("start"))
async def cmd_start(message: Message):
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("Команда работает только в группах.")
        return
    team = await get_team_by_chat_id(message.chat.id)
    if not team:
        await create_team(message.chat.id, message.chat.title or "Team")
        await message.answer(
            START_MESSAGE
            + f"\n\nЧтобы присоединиться, каждый участник пишет боту в личку ровно эту команду:\n<code>/join {message.chat.id}</code>"
        )
    else:
        await message.answer(
            f"Команда уже зарегистрирована.\n\nЧтобы присоединиться, каждый участник пишет боту в личку ровно эту команду:\n<code>/join {message.chat.id}</code>"
        )


@router.message(Command("join"))
async def cmd_join(message: Message):
    if message.chat.type != "private":
        await message.answer("Используйте команду в личных сообщениях.")
        return
    args = message.text.split()
    if len(args) < 2:
        await message.answer("Используйте: /join ID_ГРУППЫ")
        return
    try:
        chat_id = int(args[1])
    except ValueError:
        await message.answer("Неверный chat_id.")
        return

    team = await get_team_by_chat_id(chat_id)
    if not team:
        await message.answer(TEAM_NOT_FOUND)
        return

    member = await get_member_by_user_id(message.from_user.id)
    if member:
        await message.answer(ALREADY_JOINED)
        return

    await add_member(team['id'], message.from_user.id, message.from_user.username, message.from_user.full_name)
    await message.answer(JOIN_SUCCESS.format(team_name=team.get('name', 'команда')))


@router.message(Command("settime"))
async def cmd_settime(message: Message):
    if message.chat.type not in ("group", "supergroup") or not await is_admin(message.chat.id, message.from_user.id):
        await message.answer(NOT_ADMIN)
        return
    args = message.text.split()
    if len(args) != 3:
        await message.answer("Формат: /settime HH:MM HH:MM")
        return
    team = await get_team_by_chat_id(message.chat.id)
    if not team:
        await message.answer(TEAM_NOT_FOUND)
        return
    await update_team_times(team['id'], args[1], args[2])
    await message.answer(f"Время обновлено: опрос — {args[1]}, дайджест — {args[2]}")


@router.message(Command("members"))
async def cmd_members(message: Message):
    team = await get_team_by_chat_id(message.chat.id)
    if not team:
        await message.answer(TEAM_NOT_FOUND)
        return
    members = await get_team_members(team['id'])
    if not members:
        await message.answer("Нет участников.")
        return
    text = MEMBERS_LIST.format(
        members="\n".join([f"• {m['full_name']} (🔥 {m['streak_count']})" for m in members])
    )
    await message.answer(text)


@router.message(Command("pause"))
async def cmd_pause(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        await message.answer(NOT_ADMIN)
        return
    team = await get_team_by_chat_id(message.chat.id)
    if team:
        await toggle_team_active(team['id'], False)
        await message.answer(PAUSE_SUCCESS)


@router.message(Command("resume"))
async def cmd_resume(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        await message.answer(NOT_ADMIN)
        return
    team = await get_team_by_chat_id(message.chat.id)
    if team:
        await toggle_team_active(team['id'], True)
        await message.answer(RESUME_SUCCESS)


@router.message(Command("history"))
async def cmd_history(message: Message):
    team = await get_team_by_chat_id(message.chat.id)
    if not team:
        await message.answer(TEAM_NOT_FOUND)
        return
    standups = await get_team_standups(team['id'], 5)
    if not standups:
        await message.answer(HISTORY_EMPTY)
        return
    await message.answer(standups[0].get('digest_text') or 'Дайджест ещё не сформирован.')


@router.message(Command("testsurvey"))
async def cmd_testsurvey(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return
    team = await get_team_by_chat_id(message.chat.id)
    if not team:
        return
    await get_or_create_standup(team['id'], today_str())
    members = await get_team_members(team['id'])
    for m in members:
        await start_survey_for_member(m)
    await message.answer("Опросы отправлены.")


@router.message(Command("testdigest"))
async def cmd_testdigest(message: Message):
    if not await is_admin(message.chat.id, message.from_user.id):
        return
    team = await get_team_by_chat_id(message.chat.id)
    if not team:
        return
    standup = await get_or_create_standup(team['id'], today_str())
    await generate_and_send_digest(team, standup['id'], today_str())
    await message.answer("Дайджест отправлен.")


# ---------- FSM ----------
@router.message(SurveyStates.waiting_yesterday)
async def process_yesterday(message: Message, state: FSMContext):
    await state.update_data(yesterday=message.text)
    await message.answer(QUESTION_TODAY)
    await state.set_state(SurveyStates.waiting_today)


@router.message(SurveyStates.waiting_today)
async def process_today(message: Message, state: FSMContext):
    await state.update_data(today=message.text)
    await message.answer(QUESTION_BLOCKERS)
    await state.set_state(SurveyStates.waiting_blockers)


@router.message(SurveyStates.waiting_blockers)
async def process_blockers(message: Message, state: FSMContext):
    data = await state.get_data()
    member = await get_member_by_user_id(message.from_user.id)
    if not member:
        await state.clear()
        return

    standup = await get_or_create_standup(member['team_id'], today_str())

    await save_response(standup['id'], member['id'], data.get('yesterday', ''), data.get('today', ''), message.text)
    await update_member_streak(member['id'], member.get('streak_count', 0) + 1)

    await message.answer(SURVEY_COMPLETE)
    await state.clear()


async def generate_and_send_digest(team: Dict, standup_id: int, date: str):
    responses = await get_standup_responses(standup_id)
    members = await get_team_members(team['id'])
    answered = len(responses)
    total = len(members)

    digest = DIGEST_HEADER.format(date=date) + "\n\n"
    responded_ids = {r['member_id'] for r in responses}

    for r in responses:
        digest += MEMBER_LINE.format(
            name=r['full_name'],
            streak=r.get('streak_count', 0),
            yesterday=r['yesterday'],
            today=r['today'],
            blockers=r['blockers']
        ) + "\n"

    for m in members:
        if m['id'] not in responded_ids:
            digest += f"👤 {m['full_name']} {NO_RESPONSE}\n\n"

    digest += DIGEST_FOOTER.format(answered=answered, total=total)

    try:
        await bot.send_message(team['chat_id'], digest)
        await update_standup_digest(standup_id, digest)
    except Exception as e:
        logger.error(f"Ошибка отправки дайджеста: {e}")


# ---------- Scheduler: this is the second core fix ----------
# Раньше три джобы стояли на IntervalTrigger(minutes=1) и никогда не сверялись
# с survey_time/digest_time команды -> бот слал опрос/напоминание/дайджест
# каждую минуту 24/7 всем командам. Теперь одна джоба раз в минуту сверяет
# текущее HH:MM с настройками команды и стреляет ровно один раз в нужный момент,
# используя существование standup как флаг "уже отправлено сегодня".
async def scheduler_tick():
    current_hhmm = now_tz().strftime("%H:%M")
    if now_tz().weekday() >= 5:  # суббота/воскресенье - пропускаем (будни-стендап)
        return
    date = today_str()

    for team in await get_active_teams():
        survey_time = team['survey_time']
        digest_time = team['digest_time']
        reminder_time = add_minutes_to_hhmm(survey_time, team['reminder_delay_min'])

        existing_standup = await get_standup_if_exists(team['id'], date)

        # 1) время опроса — отправляем вопросы только если стендапа на сегодня ещё нет
        if current_hhmm == survey_time and not existing_standup:
            await get_or_create_standup(team['id'], date)
            for member in await get_team_members(team['id']):
                await start_survey_for_member(member)
            continue  # standup только что создан, дальше в этом тике делать нечего

        if not existing_standup:
            continue

        # 2) время напоминания — только тем, кто ещё не ответил
        if current_hhmm == reminder_time:
            members = await get_team_members(team['id'])
            unresponded = await get_unresponded_members(existing_standup['id'], members)
            for m in unresponded:
                try:
                    text = random.choice(REMINDER_MESSAGES).format(name=m['full_name'].split()[0])
                    await bot.send_message(m['user_id'], text)
                except Exception as e:
                    logger.warning(f"Не удалось отправить напоминание {m['user_id']}: {e}")

        # 3) время дайджеста — только если ещё не отправлен сегодня
        if current_hhmm == digest_time and existing_standup.get('status') != 'sent':
            await generate_and_send_digest(team, existing_standup['id'], date)


@dp.startup()
async def on_startup():
    await init_db()
    scheduler.add_job(scheduler_tick, IntervalTrigger(minutes=1))
    scheduler.start()
    logger.info("Бот запущен")


@dp.shutdown()
async def on_shutdown():
    scheduler.shutdown()
    await bot.session.close()


if __name__ == "__main__":
    asyncio.run(dp.run_polling(bot))
