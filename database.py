"""
database.py — работа с SQLite базой данных
"""

import aiosqlite
import json
from typing import Optional

DB_PATH = "pullup.db"


async def init_db():
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS users (
                user_id         INTEGER PRIMARY KEY,
                username        TEXT,
                current_max     INTEGER NOT NULL DEFAULT 1,
                cycle_day       INTEGER NOT NULL DEFAULT 1,
                is_rest_day     INTEGER NOT NULL DEFAULT 0,
                total_workouts  INTEGER NOT NULL DEFAULT 0,
                created_at      TEXT DEFAULT (datetime('now'))
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS workout_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                cycle_day   INTEGER NOT NULL,
                planned     TEXT NOT NULL,
                actual      TEXT,
                completed   INTEGER DEFAULT 0,
                logged_at   TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS max_history (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                max_reps    INTEGER NOT NULL,
                recorded_at TEXT DEFAULT (datetime('now')),
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        await db.commit()


async def get_user(user_id: int) -> Optional[dict]:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)) as cursor:
            row = await cursor.fetchone()
            return dict(row) if row else None


async def create_user(user_id: int, username: str, current_max: int):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users (user_id, username, current_max) VALUES (?, ?, ?)",
            (user_id, username or "", current_max),
        )
        await db.execute(
            "INSERT INTO max_history (user_id, max_reps) VALUES (?, ?)",
            (user_id, current_max),
        )
        await db.commit()


async def update_max(user_id: int, new_max: int):
    """Обновляет максимум и сбрасывает цикл."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET current_max = ?, cycle_day = 1, is_rest_day = 0 WHERE user_id = ?",
            (new_max, user_id),
        )
        await db.execute(
            "INSERT INTO max_history (user_id, max_reps) VALUES (?, ?)",
            (user_id, new_max),
        )
        await db.commit()


async def reset_cycle(user_id: int):
    """Сбрасывает только цикл, максимум остаётся."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "UPDATE users SET cycle_day = 1, is_rest_day = 0 WHERE user_id = ?",
            (user_id,),
        )
        await db.commit()


async def advance_day(user_id: int):
    user = await get_user(user_id)
    if not user:
        return
    cycle_day = user["cycle_day"]
    is_rest = user["is_rest_day"]
    async with aiosqlite.connect(DB_PATH) as db:
        if is_rest:
            next_day = cycle_day + 1 if cycle_day < 4 else 1
            await db.execute(
                "UPDATE users SET cycle_day = ?, is_rest_day = 0 WHERE user_id = ?",
                (next_day, user_id),
            )
        else:
            await db.execute(
                "UPDATE users SET is_rest_day = 1, total_workouts = total_workouts + 1 WHERE user_id = ?",
                (user_id,),
            )
        await db.commit()


async def log_workout(user_id: int, cycle_day: int, planned: str, actual: str, completed: bool):
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            "INSERT INTO workout_log (user_id, cycle_day, planned, actual, completed) VALUES (?, ?, ?, ?, ?)",
            (user_id, cycle_day, planned, actual, int(completed)),
        )
        await db.commit()


async def get_completed_days_this_cycle(user_id: int) -> list:
    """Возвращает список выполненных дней в текущем цикле (1, 2, 3)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        # Берём последние записи — дни текущего цикла
        # Цикл сбрасывается при update_max/reset_cycle, поэтому берём записи после последнего сброса
        async with db.execute("""
            SELECT cycle_day FROM workout_log
            WHERE user_id = ? AND cycle_day IN (1, 2, 3) AND completed = 1
            ORDER BY logged_at DESC LIMIT 3
        """, (user_id,)) as cursor:
            rows = await cursor.fetchall()
        return [r["cycle_day"] for r in rows]


async def get_stats(user_id: int) -> dict:
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row

        async with db.execute(
            "SELECT current_max, total_workouts FROM users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            if not row:
                return {}

        async with db.execute("""
            SELECT COUNT(*) as total, SUM(completed) as done
            FROM workout_log
            WHERE user_id = ? AND logged_at >= datetime('now', '-7 days')
        """, (user_id,)) as cursor:
            week = await cursor.fetchone()

        async with db.execute("""
            SELECT actual FROM workout_log
            WHERE user_id = ? AND actual IS NOT NULL AND actual != ''
              AND logged_at >= datetime('now', '-7 days')
        """, (user_id,)) as cursor:
            rows = await cursor.fetchall()

        week_volume = 0
        for r in rows:
            try:
                week_volume += sum(json.loads(r["actual"]))
            except Exception:
                pass

        async with db.execute("""
            SELECT COUNT(*) as total, SUM(completed) as done
            FROM workout_log WHERE user_id = ?
        """, (user_id,)) as cursor:
            all_time = await cursor.fetchone()

        completion_pct = 0
        if all_time["total"] and all_time["total"] > 0:
            completion_pct = round((all_time["done"] or 0) / all_time["total"] * 100)

        async with db.execute("""
            SELECT max_reps FROM max_history
            WHERE user_id = ? ORDER BY recorded_at ASC
        """, (user_id,)) as cursor:
            history_rows = await cursor.fetchall()

        max_history = [r["max_reps"] for r in history_rows]

        return {
            "current_max": row["current_max"],
            "total_workouts": row["total_workouts"],
            "week_workouts": week["total"] or 0,
            "week_done": week["done"] or 0,
            "week_volume": week_volume,
            "completion_pct": completion_pct,
            "max_history": max_history,
        }