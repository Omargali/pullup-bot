"""
programs.py — алгоритм прогрессии подтягиваний до 100
"""

from dataclasses import dataclass
from typing import List


@dataclass
class Workout:
    day: int           # 1, 2 или 3
    sets: List[int]    # повторения в каждом подходе
    total: int         # суммарный объём
    rest_seconds: int  # отдых между подходами


def generate_cycle(current_max: int) -> List[Workout]:
    """
    Генерирует цикл из 3 тренировок на основе текущего максимума.

    Формула (референс: приложение на скриншоте):
        base = current_max // 2

        День 1 (лёгкий):   [base, base-1, base-1, base-1, base-2]  отдых 30 сек
        День 2 (средний):  [base, base,   base-1, base-1, base-1]  отдых 60 сек
        День 3 (тяжёлый):  [base, base,   base,   base-1, base-1]  отдых 90 сек
    """
    if current_max < 2:
        current_max = 2

    b = current_max // 2

    workouts = [
        Workout(
            day=1,
            sets=[b, b-1, b-1, b-1, max(1, b-2)],
            total=0,
            rest_seconds=30,
        ),
        Workout(
            day=2,
            sets=[b, b, b-1, b-1, b-1],
            total=0,
            rest_seconds=60,
        ),
        Workout(
            day=3,
            sets=[b, b, b, b-1, b-1],
            total=0,
            rest_seconds=90,
        ),
    ]

    for w in workouts:
        w.sets = [max(1, s) for s in w.sets]
        w.total = sum(w.sets)

    return workouts


def format_workout(workout: Workout) -> str:
    """Форматирует тренировку в текст для Telegram."""
    sets_str = "  ".join(str(s) for s in workout.sets)

    minutes = workout.rest_seconds // 60
    seconds = workout.rest_seconds % 60
    rest_str = f"{minutes:02d}:{seconds:02d}"

    day_labels = {1: "🟢 Лёгкий", 2: "🟡 Средний", 3: "🔴 Тяжёлый"}
    label = day_labels.get(workout.day, f"День {workout.day}")

    return (
        f"*День {workout.day} — {label}*\n\n"
        f"`{sets_str}`\n\n"
        f"📊 Итого: *{workout.total}* подтягиваний\n"
        f"⏱ Отдых между подходами: *{rest_str}*"
    )


def format_cycle_plan(workouts: List[Workout]) -> str:
    """Форматирует весь план цикла одним сообщением."""
    lines = ["📋 *План цикла:*\n"]
    for w in workouts:
        sets_str = "  ".join(str(s) for s in w.sets)
        minutes = w.rest_seconds // 60
        seconds = w.rest_seconds % 60
        rest_str = f"{minutes:02d}:{seconds:02d}"
        lines.append(f"День {w.day}: `{sets_str}` — отдых {rest_str}")
    lines.append("\nПосле дня 3 → день отдыха → *Тест максимума* 🏆")
    return "\n".join(lines)


def calculate_progress(current_max: int, goal: int = 100) -> float:
    return min(round((current_max / goal) * 100, 1), 100.0)


def get_motivation(current_max: int, goal: int = 100) -> str:
    pct = calculate_progress(current_max, goal)
    if pct < 15:
        return "🌱 Начало пути — главное, что ты уже начал!"
    elif pct < 30:
        return "🔥 Хороший старт! Прогресс уже есть."
    elif pct < 50:
        return "💪 Четверть пути позади. Темп набран!"
    elif pct < 75:
        return "⚡ Больше половины! Ты точно дойдёшь до 100."
    elif pct < 90:
        return "🚀 Финишная прямая! Совсем немного осталось."
    else:
        return "🏆 Ты почти у цели. 100 подтягиваний — это реально!"
