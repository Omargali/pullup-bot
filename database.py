"""
database.py — работа с SQLite базой данных
"""

import aiosqlite
from typing import Optional

DB_PATH = "pullup.db"


async def init_db():
    """Создаёт таблицы при первом запуске."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id     INTEGER PRIMARY KEY,
                username    TEXT,
                current_max INTEGER NOT NULL DEFAULT 1,
                cycle_day   INTEGER NOT NULL DEFAULT 1,  -- 1, 2, 3, или 4 (тест)
                is_rest_day INTEGER NOT NULL DEFAULT 0,  -- 1 = сегодня отдых
                total_workouts INTEGER NOT NULL DEFAULT 0,
                created_at  TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS workout_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                cycle_day   INTEGER NOT NULL,   -- 1, 2, 3
                planned     TEXT NOT NULL,      -- JSON: [3,2,2,2,1]
                actual      TEXT,               -- JSON: фактически сделано
                completed   INTEGER DEFAULT 0,
                logged_at   TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        await db.commit()


async def get_user(user_id: int) -> Optional[dict]:
    """Возвращает данные пользователя или None если не найден."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def create_user(user_id: int, username: str, current_max: int):
    """Регистрирует нового пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR IGNORE INTO users (user_id, username, current_max)
            VALUES (?, ?, ?)
            """,
            (user_id, username or "", current_max),
        )
        await db.commit()


async def update_max(user_id: int, new_max: int):
    """Обновляет максимум после теста и сбрасывает цикл."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE users
            SET current_max = ?, cycle_day = 1, is_rest_day = 0
            WHERE user_id = ?
            """,
            (new_max, user_id),
        )
        await db.commit()


async def advance_day(user_id: int):
    """
    Продвигает пользователя на следующий шаг цикла:
    1 → отдых → 2 → отдых → 3 → отдых → тест(4) → сброс на 1
    """
    user = await get_user(user_id)
    if not user:
        return

    cycle_day = user["cycle_day"]
    is_rest = user["is_rest_day"]

    async with aiosqlite.connect(DB_PATH) as db:
        if is_rest:
            # Закончили день отдыха — переходим к следующему тренировочному дню
            next_day = cycle_day + 1 if cycle_day < 4 else 1
            await db.execute(
                "UPDATE users SET cycle_day = ?, is_rest_day = 0 WHERE user_id = ?",
                (next_day, user_id),
            )
        else:
            # Закончили тренировку — теперь день отдыха
            await db.execute(
                "UPDATE users SET is_rest_day = 1, total_workouts = total_workouts + 1 WHERE user_id = ?",
                (user_id,),
            )
        await db.commit()


async def log_workout(user_id: int, cycle_day: int, planned: str, actual: str, completed: bool):
    """Записывает результат тренировки в лог."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO workout_log (user_id, cycle_day, planned, actual, completed)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user_id, cycle_day, planned, actual, int(completed)),
        )
        await db.commit()


async def get_stats(user_id: int) -> dict:
    """Возвращает статистику пользователя."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT current_max, total_workouts FROM users WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return {}

        async with db.execute(
            "SELECT COUNT(*) as total, SUM(completed) as done FROM workout_log WHERE user_id = ?",
            (user_id,)
        ) as cursor:
            log = await cursor.fetchone()

        return {
            "current_max": row["current_max"],
            "total_workouts": row["total_workouts"],
            "logged": log["total"] or 0,
            "completed": log["done"] or 0,
        }
