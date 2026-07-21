import aiosqlite
from datetime import datetime
from typing import List, Optional, Dict

from config import DB_PATH


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.executescript('''
            CREATE TABLE IF NOT EXISTS teams (
                id INTEGER PRIMARY KEY,
                chat_id INTEGER UNIQUE,
                name TEXT,
                survey_time TEXT DEFAULT '10:00',
                digest_time TEXT DEFAULT '10:30',
                reminder_delay_min INTEGER DEFAULT 30,
                is_active BOOLEAN DEFAULT 1,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS members (
                id INTEGER PRIMARY KEY,
                team_id INTEGER,
                user_id INTEGER,
                username TEXT,
                full_name TEXT,
                is_active BOOLEAN DEFAULT 1,
                streak_count INTEGER DEFAULT 0,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (team_id) REFERENCES teams(id)
            );

            CREATE TABLE IF NOT EXISTS standups (
                id INTEGER PRIMARY KEY,
                team_id INTEGER,
                date TEXT,
                status TEXT DEFAULT 'collecting',
                digest_text TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (team_id) REFERENCES teams(id),
                UNIQUE(team_id, date)
            );

            CREATE TABLE IF NOT EXISTS responses (
                id INTEGER PRIMARY KEY,
                standup_id INTEGER,
                member_id INTEGER,
                yesterday TEXT,
                today TEXT,
                blockers TEXT,
                answered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (standup_id) REFERENCES standups(id),
                FOREIGN KEY (member_id) REFERENCES members(id)
            );
        ''')
        await db.commit()


async def get_team_by_chat_id(chat_id: int) -> Optional[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM teams WHERE chat_id = ?", (chat_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def create_team(chat_id: int, name: str) -> Optional[int]:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("INSERT OR IGNORE INTO teams (chat_id, name) VALUES (?, ?)", (chat_id, name))
        await db.commit()
        team = await get_team_by_chat_id(chat_id)
        return team['id'] if team else None


async def update_team_times(team_id: int, survey_time: str, digest_time: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE teams SET survey_time=?, digest_time=? WHERE id=?", (survey_time, digest_time, team_id))
        await db.commit()


async def toggle_team_active(team_id: int, is_active: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE teams SET is_active=? WHERE id=?", (is_active, team_id))
        await db.commit()


async def get_active_teams() -> List[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM teams WHERE is_active=1") as cursor:
            return [dict(row) for row in await cursor.fetchall()]


async def get_member_by_user_id(user_id: int) -> Optional[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM members WHERE user_id=?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def add_member(team_id: int, user_id: int, username: str, full_name: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO members (team_id, user_id, username, full_name) VALUES (?, ?, ?, ?)",
            (team_id, user_id, username, full_name)
        )
        await db.commit()


async def get_team_members(team_id: int) -> List[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM members WHERE team_id=? AND is_active=1", (team_id,)
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]


async def get_standup_if_exists(team_id: int, date: str) -> Optional[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM standups WHERE team_id=? AND date=?", (team_id, date)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def get_or_create_standup(team_id: int, date: str) -> Dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM standups WHERE team_id=? AND date=?", (team_id, date)
        ) as cursor:
            row = await cursor.fetchone()
            if row:
                return dict(row)

        await db.execute("INSERT INTO standups (team_id, date) VALUES (?, ?)", (team_id, date))
        await db.commit()
        async with db.execute("SELECT * FROM standups WHERE id=last_insert_rowid()") as cursor:
            return dict(await cursor.fetchone())


async def save_response(standup_id: int, member_id: int, yesterday: str, today: str, blockers: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR REPLACE INTO responses (standup_id, member_id, yesterday, today, blockers) VALUES (?, ?, ?, ?, ?)",
            (standup_id, member_id, yesterday, today, blockers)
        )
        await db.commit()


async def get_standup_responses(standup_id: int) -> List[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("""
            SELECT r.*, m.full_name, m.streak_count 
            FROM responses r JOIN members m ON r.member_id = m.id 
            WHERE r.standup_id=?
        """, (standup_id,)) as cursor:
            return [dict(row) for row in await cursor.fetchall()]


async def get_team_standups(team_id: int, limit: int = 5) -> List[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM standups WHERE team_id=? ORDER BY date DESC LIMIT ?",
            (team_id, limit)
        ) as cursor:
            return [dict(row) for row in await cursor.fetchall()]


async def update_standup_digest(standup_id: int, digest_text: str):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE standups SET digest_text=?, status='sent' WHERE id=?", (digest_text, standup_id))
        await db.commit()


async def update_member_streak(member_id: int, streak: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("UPDATE members SET streak_count=? WHERE id=?", (streak, member_id))
        await db.commit()


async def get_unresponded_members(standup_id: int, team_members: List[Dict]) -> List[Dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT member_id FROM responses WHERE standup_id=?", (standup_id,)) as cursor:
            responded = {row[0] for row in await cursor.fetchall()}
    return [m for m in team_members if m['id'] not in responded]
