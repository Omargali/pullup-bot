"""
handlers.py — интерактивные тренировки с подходами, таймером и статистикой
"""

import json
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes

from database import get_user, create_user, update_max, advance_day, log_workout, get_stats
from programs import generate_cycle, format_workout, format_cycle_plan, calculate_progress, get_motivation


# ──────────────────────── Главная клавиатура ──────────────────

MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("💪 Тренировка"), KeyboardButton("📋 План")],
        [KeyboardButton("📊 Прогресс"),   KeyboardButton("❓ Помощь")],
    ],
    resize_keyboard=True,
)


# ─────────────────────────── /start ───────────────────────────

async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await get_user(user_id)

    if user:
        await update.message.reply_text(
            f"👋 С возвращением! Твой максимум: *{user['current_max']}* подтягиваний.\n\n"
            "Нажми *💪 Тренировка* чтобы начать.",
            parse_mode="Markdown",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    await update.message.reply_text(
        "👋 Привет! Бот для прогрессии подтягиваний.\n\n"
        "Цель — *100 подтягиваний* 🏆\n\n"
        "Сколько подтягиваний ты можешь сделать *максимум* прямо сейчас?\n\n"
        "Напиши число, например: `6`",
        parse_mode="Markdown",
    )
    context.user_data["waiting_for_max"] = True


# ─────────────────────── Ввод текста ──────────────────────────

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    text = update.message.text.strip()

    if text == "💪 Тренировка":
        await cmd_workout(update, context)
        return
    if text == "📋 План":
        await cmd_plan(update, context)
        return
    if text == "📊 Прогресс":
        await cmd_progress(update, context)
        return
    if text == "❓ Помощь":
        await cmd_help(update, context)
        return

    # Ввод начального максимума
    if context.user_data.get("waiting_for_max"):
        if not text.isdigit() or int(text) < 1:
            await update.message.reply_text("❗ Введи число больше 0, например: `6`", parse_mode="Markdown")
            return
        max_reps = int(text)
        username = update.effective_user.username or update.effective_user.first_name
        await create_user(user_id, username, max_reps)
        context.user_data.pop("waiting_for_max", None)
        workouts = generate_cycle(max_reps)
        await update.message.reply_text(
            f"✅ Записал максимум: *{max_reps}* подтягиваний\n"
            f"📈 Прогресс к цели 100: *{calculate_progress(max_reps)}%*\n\n"
            f"{get_motivation(max_reps)}\n\n"
            f"{format_cycle_plan(workouts)}",
            parse_mode="Markdown",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    # Ввод результата теста максимума
    if context.user_data.get("waiting_for_test"):
        if not text.isdigit() or int(text) < 1:
            await update.message.reply_text("❗ Введи число больше 0", parse_mode="Markdown")
            return
        new_max = int(text)
        old_max = context.user_data.pop("old_max", 0)
        context.user_data.pop("waiting_for_test", None)
        await update_max(user_id, new_max)
        workouts = generate_cycle(new_max)
        diff = new_max - old_max
        diff_str = f"+{diff}" if diff > 0 else str(diff)
        await update.message.reply_text(
            f"🏆 *Тест завершён!*\n\n"
            f"Было: *{old_max}* → Стало: *{new_max}* ({diff_str})\n"
            f"📈 Прогресс: *{calculate_progress(new_max)}%*\n\n"
            f"{get_motivation(new_max)}\n\n"
            f"Новый цикл:\n{format_cycle_plan(workouts)}",
            parse_mode="Markdown",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    await update.message.reply_text("Используй кнопки внизу 👇", reply_markup=MAIN_KEYBOARD)


# ───────────────────── Показать подход ────────────────────────

async def show_set(update_or_query, context: ContextTypes.DEFAULT_TYPE, edit: bool = False):
    """Показывает текущий подход с кнопками +/- и Готово."""
    state = context.user_data.get("workout_state")
    if not state:
        return

    idx = state["set_index"]
    sets = state["sets"]
    actual = state["actual"]
    total_sets = len(sets)
    planned_reps = sets[idx]

    while len(actual) <= idx:
        actual.append(sets[idx])
    current_reps = actual[idx]

    done_so_far = sum(actual[:idx])

    text = (
        f"💪 *Подход {idx + 1} из {total_sets}*\n\n"
        f"По плану: *{planned_reps}*\n\n"
        f"Сколько сделал?\n\n"
        f"*{current_reps}*\n\n"
        f"Уже выполнено: *{done_so_far}* подтягиваний"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➖", callback_data="set_minus"),
            InlineKeyboardButton(f"  {current_reps}  ", callback_data="set_noop"),
            InlineKeyboardButton("➕", callback_data="set_plus"),
        ],
        [InlineKeyboardButton("✅ Готово", callback_data="set_done")],
    ])

    if edit and hasattr(update_or_query, "edit_message_text"):
        await update_or_query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
    else:
        await update_or_query.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


# ─────────────────────────── /workout ─────────────────────────

async def cmd_workout(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await get_user(user_id)

    if not user:
        await update.message.reply_text("Сначала запусти /start и введи максимум.")
        return

    if user["is_rest_day"]:
        await update.message.reply_text(
            "😴 *Сегодня день отдыха.*\n\n"
            "Мышцы растут именно сейчас 💪\n"
            "Завтра — следующая тренировка.",
            parse_mode="Markdown",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    cycle_day = user["cycle_day"]

    if cycle_day == 4:
        context.user_data["waiting_for_test"] = True
        context.user_data["old_max"] = user["current_max"]
        await update.message.reply_text(
            "🏆 *День теста максимума!*\n\n"
            f"Предыдущий максимум: *{user['current_max']}*\n\n"
            "Сделай максимальное количество подтягиваний за один подход — до отказа.\n\n"
            "Введи результат:",
            parse_mode="Markdown",
            reply_markup=MAIN_KEYBOARD,
        )
        return

    workouts = generate_cycle(user["current_max"])
    workout = workouts[cycle_day - 1]

    context.user_data["workout_state"] = {
        "cycle_day": cycle_day,
        "sets": workout.sets,
        "actual": [workout.sets[0]],
        "set_index": 0,
        "rest_seconds": workout.rest_seconds,
        "planned_json": json.dumps(workout.sets),
    }

    day_label = {1: "🟢 Лёгкий", 2: "🟡 Средний", 3: "🔴 Тяжёлый"}.get(cycle_day, "")
    await update.message.reply_text(
        f"*День {cycle_day} из 3 — {day_label}*\n\n"
        f"План: `{'  '.join(str(s) for s in workout.sets)}`\n"
        f"Итого: *{workout.total}* подтягиваний\n"
        f"Отдых между подходами: *{workout.rest_seconds // 60:02d}:{workout.rest_seconds % 60:02d}*\n\n"
        f"Начинаем! 👇",
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD,
    )
    await show_set(update, context)


# ───────────────────── Колбэки подходов ───────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    state = context.user_data.get("workout_state")

    # ── +/- повторений ──
    if data in ("set_plus", "set_minus", "set_noop"):
        if not state:
            await query.edit_message_text("❗ Начни тренировку через 💪 Тренировка")
            return
        idx = state["set_index"]
        while len(state["actual"]) <= idx:
            state["actual"].append(state["sets"][idx])

        if data == "set_plus":
            state["actual"][idx] = min(state["actual"][idx] + 1, 99)
        elif data == "set_minus":
            state["actual"][idx] = max(state["actual"][idx] - 1, 0)

        await show_set(query, context, edit=True)
        return

    # ── Подход выполнен ──
    if data == "set_done":
        if not state:
            await query.edit_message_text("❗ Начни тренировку через 💪 Тренировка")
            return

        idx = state["set_index"]
        sets = state["sets"]
        total_sets = len(sets)

        while len(state["actual"]) <= idx:
            state["actual"].append(sets[idx])

        done_reps = state["actual"][idx]

        # Последний подход — тренировка завершена
        if idx + 1 >= total_sets:
            actual_list = state["actual"]
            actual_json = json.dumps(actual_list)
            planned_json = state["planned_json"]
            cycle_day = state["cycle_day"]
            total_actual = sum(actual_list)
            total_planned = sum(sets)
            completed = total_actual >= total_planned * 0.8

            await log_workout(user_id, cycle_day, planned_json, actual_json, completed)
            await advance_day(user_id)
            context.user_data.pop("workout_state", None)

            sets_str = "  ".join(str(r) for r in actual_list)
            if cycle_day == 3:
                next_msg = "Следующий шаг — отдых, затем *Тест максимума* 🏆"
            else:
                next_msg = f"Следующий шаг — отдых, затем *День {cycle_day + 1}*"

            status = "✅ Выполнено!" if completed else "💪 Сделал что смог!"

            await query.edit_message_text(
                f"{status}\n\n"
                f"*Результат:*\n`{sets_str}`\n\n"
                f"Сделано: *{total_actual}* / {total_planned} подтягиваний\n\n"
                f"{next_msg}",
                parse_mode="Markdown",
            )
            return

        # Не последний подход — показываем сообщение об отдыхе
        rest = state["rest_seconds"]
        state["set_index"] = idx + 1
        while len(state["actual"]) <= idx + 1:
            state["actual"].append(sets[idx + 1])

        mins = rest // 60
        secs = rest % 60

        # Редактируем сообщение — показываем что идёт отдых
        await query.edit_message_text(
            f"✅ Подход {idx + 1} выполнен: *{done_reps}* повторений\n\n"
            f"⏱ Отдых *{mins:02d}:{secs:02d}*...\n\n"
            f"Следующий подход {idx + 2} из {total_sets} → план *{sets[idx + 1]}*\n\n"
            f"_Жди уведомления когда время выйдет_",
            parse_mode="Markdown",
        )

        # Ждём в фоне и отправляем уведомление
        chat_id = query.message.chat_id
        bot = context.bot

        await asyncio.sleep(rest)

        # Проверяем что пользователь не прервал тренировку
        if not context.user_data.get("workout_state"):
            return

        # Уведомление — время вышло
        await bot.send_message(
            chat_id=chat_id,
            text=f"🔔 *Отдых закончился!*\n\nПодход {idx + 2} из {total_sets} → план *{sets[idx + 1]}*",
            parse_mode="Markdown",
        )

        # Показываем следующий подход новым сообщением
        await show_set_by_chat(bot, chat_id, context, idx + 1, sets, total_sets)
        return


async def show_set_by_chat(bot, chat_id: int, context: ContextTypes.DEFAULT_TYPE, idx: int, sets: list, total_sets: int):
    """Отправляет новое сообщение с подходом после таймера."""
    state = context.user_data.get("workout_state")
    if not state:
        return

    while len(state["actual"]) <= idx:
        state["actual"].append(sets[idx])

    current_reps = state["actual"][idx]
    done_so_far = sum(state["actual"][:idx])

    text = (
        f"💪 *Подход {idx + 1} из {total_sets}*\n\n"
        f"По плану: *{sets[idx]}*\n\n"
        f"Сколько сделал?\n\n"
        f"*{current_reps}*\n\n"
        f"Уже выполнено: *{done_so_far}* подтягиваний"
    )

    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("➖", callback_data="set_minus"),
            InlineKeyboardButton(f"  {current_reps}  ", callback_data="set_noop"),
            InlineKeyboardButton("➕", callback_data="set_plus"),
        ],
        [InlineKeyboardButton("✅ Готово", callback_data="set_done")],
    ])

    await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown", reply_markup=keyboard)


# ─────────────────────────── /progress ────────────────────────

async def cmd_progress(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    stats = await get_stats(user_id)

    if not stats:
        await update.message.reply_text("Сначала запусти /start.", reply_markup=MAIN_KEYBOARD)
        return

    current_max = stats["current_max"]
    progress = calculate_progress(current_max)
    filled = int(progress // 5)
    bar = "█" * filled + "░" * (20 - filled)

    week_pct = 0
    if stats["week_workouts"] > 0:
        week_pct = round((stats["week_done"] or 0) / stats["week_workouts"] * 100)

    # Динамика максимума
    max_history = stats.get("max_history", [])
    if max_history:
        history_str = " → ".join(str(m) for m in max_history)
        history_line = f"  • Динамика: *{history_str}*\n"
    else:
        history_line = ""

    await update.message.reply_text(
        f"📊 *Статистика*\n\n"
        f"🎯 Цель: *100* подтягиваний\n"
        f"💪 Максимум сейчас: *{current_max}*\n"
        f"`{bar}`\n"
        f"*{progress}%* к цели\n\n"
        f"📅 *За эту неделю:*\n"
        f"  • Тренировок: *{stats['week_workouts']}* из 3\n"
        f"  • Объём: *{stats['week_volume']}* подтягиваний\n"
        f"  • Выполнение плана: *{week_pct}%*\n\n"
        f"📈 *За всё время:*\n"
        f"  • Тренировок: *{stats['total_workouts']}*\n"
        f"  • Выполнение плана: *{stats['completion_pct']}%*\n"
        f"{history_line}\n"
        f"{get_motivation(current_max)}",
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD,
    )


# ─────────────────────────── /plan ────────────────────────────

async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await get_user(user_id)
    if not user:
        await update.message.reply_text("Сначала запусти /start.", reply_markup=MAIN_KEYBOARD)
        return
    workouts = generate_cycle(user["current_max"])
    await update.message.reply_text(
        f"Текущий максимум: *{user['current_max']}*\n\n{format_cycle_plan(workouts)}",
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD,
    )


# ─────────────────────────── /help ────────────────────────────

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Команды:*\n\n"
        "💪 *Тренировка* — начать тренировку дня\n"
        "📋 *План* — план текущего цикла\n"
        "📊 *Прогресс* — статистика за неделю\n"
        "❓ *Помощь* — этот список\n\n"
        "/start — перезапуск",
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD,
    )