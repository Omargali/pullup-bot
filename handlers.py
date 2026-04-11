"""
handlers.py — интерактивные тренировки с подходами, таймером и статистикой
"""

import json
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import ContextTypes

from database import (
    get_user, create_user, update_max, reset_cycle,
    advance_day, log_workout, get_stats, get_completed_days_this_cycle
)
from programs import generate_cycle, format_cycle_plan, calculate_progress, get_motivation


MAIN_KEYBOARD = ReplyKeyboardMarkup(
    [
        [KeyboardButton("💪 Тренировка"), KeyboardButton("📋 План")],
        [KeyboardButton("📊 Прогресс"),   KeyboardButton("⚙️ Настройки")],
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


# ─────────────────────── Настройки ────────────────────────────

async def cmd_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await get_user(user_id)
    if not user:
        await update.message.reply_text("Сначала запусти /start.")
        return

    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Изменить максимум", callback_data="settings_setmax")],
        [InlineKeyboardButton("🔄 Сбросить цикл",     callback_data="settings_reset")],
    ])

    await update.message.reply_text(
        f"⚙️ *Настройки*\n\n"
        f"Текущий максимум: *{user['current_max']}* подтягиваний\n"
        f"День цикла: *{user['cycle_day']}*",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )


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
    if text == "⚙️ Настройки":
        await cmd_settings(update, context)
        return

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

    if context.user_data.get("waiting_for_setmax"):
        if not text.isdigit() or int(text) < 1:
            await update.message.reply_text("❗ Введи число больше 0", parse_mode="Markdown")
            return
        new_max = int(text)
        old_max = context.user_data.pop("old_max_setmax", 0)
        context.user_data.pop("waiting_for_setmax", None)
        context.user_data.pop("workout_state", None)  # сбрасываем активную тренировку
        await update_max(user_id, new_max)
        workouts = generate_cycle(new_max)
        diff = new_max - old_max
        diff_str = f"+{diff}" if diff > 0 else str(diff)
        await update.message.reply_text(
            f"✅ *Максимум обновлён!*\n\n"
            f"Было: *{old_max}* → Стало: *{new_max}* ({diff_str})\n\n"
            f"Цикл сброшен. Новый план:\n\n{format_cycle_plan(workouts)}",
            parse_mode="Markdown",
            reply_markup=MAIN_KEYBOARD,
        )
        return

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
    state = context.user_data.get("workout_state")
    if not state:
        return

    idx = state["set_index"]
    sets = state["sets"]
    actual = state["actual"]
    total_sets = len(sets)

    while len(actual) <= idx:
        actual.append(sets[idx])

    current_reps = actual[idx]
    done_so_far = sum(actual[:idx])

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

    # БАГ 1 ИСПРАВЛЕН: защита от повторного запуска тренировки
    if context.user_data.get("workout_state"):
        await update.message.reply_text(
            "⚠️ Тренировка уже идёт!\n\n"
            "Заверши текущий подход или нажми /cancel чтобы отменить тренировку.",
            parse_mode="Markdown",
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
        "processing": False,  # БАГ 3: флаг защиты от двойного нажатия
    }

    day_label = {1: "🟢 Лёгкий", 2: "🟡 Средний", 3: "🔴 Тяжёлый"}.get(cycle_day, "")
    await update.message.reply_text(
        f"*День {cycle_day} из 3 — {day_label}*\n\n"
        f"План: `{'  '.join(str(s) for s in workout.sets)}`\n"
        f"Итого: *{workout.total}* подтягиваний\n"
        f"Отдых: *{workout.rest_seconds // 60:02d}:{workout.rest_seconds % 60:02d}*\n\n"
        f"Начинаем! 👇",
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD,
    )
    await show_set(update, context)


# ─────────────────────────── /cancel ──────────────────────────

async def cmd_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if context.user_data.get("workout_state"):
        context.user_data.pop("workout_state", None)
        await update.message.reply_text(
            "❌ Тренировка отменена.\n\nНажми *💪 Тренировка* когда будешь готов.",
            parse_mode="Markdown",
            reply_markup=MAIN_KEYBOARD,
        )
    else:
        await update.message.reply_text("Нет активной тренировки.", reply_markup=MAIN_KEYBOARD)


# ───────────────────── Колбэки ────────────────────────────────

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    data = query.data

    # ── Настройки ──
    if data == "settings_setmax":
        user = await get_user(user_id)
        context.user_data["waiting_for_setmax"] = True
        context.user_data["old_max_setmax"] = user["current_max"] if user else 0
        await query.edit_message_text(
            f"✏️ *Изменить максимум*\n\n"
            f"Текущий максимум: *{user['current_max']}*\n\n"
            f"Введи новое число:",
            parse_mode="Markdown",
        )
        return

    if data == "settings_reset":
        keyboard = InlineKeyboardMarkup([
            [
                InlineKeyboardButton("✅ Да, сбросить", callback_data="settings_reset_confirm"),
                InlineKeyboardButton("❌ Отмена",       callback_data="settings_reset_cancel"),
            ]
        ])
        await query.edit_message_text(
            "🔄 *Сбросить цикл?*\n\n"
            "Цикл начнётся заново с Дня 1.\n"
            "Максимум и история сохранятся.",
            parse_mode="Markdown",
            reply_markup=keyboard,
        )
        return

    if data == "settings_reset_confirm":
        context.user_data.pop("workout_state", None)  # отменяем активную тренировку
        await reset_cycle(user_id)
        await query.edit_message_text(
            "✅ *Цикл сброшен!*\n\nНачинаем с Дня 1. Нажми *💪 Тренировка*.",
            parse_mode="Markdown",
        )
        return

    if data == "settings_reset_cancel":
        await query.edit_message_text("Отмена. Ничего не изменилось.")
        return

    # ── Подходы ──
    state = context.user_data.get("workout_state")

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

    if data == "set_done":
        if not state:
            await query.edit_message_text("❗ Начни тренировку через 💪 Тренировка")
            return

        # БАГ 3 ИСПРАВЛЕН: защита от двойного нажатия
        if state.get("processing"):
            return
        state["processing"] = True

        idx = state["set_index"]
        sets = state["sets"]
        total_sets = len(sets)

        while len(state["actual"]) <= idx:
            state["actual"].append(sets[idx])

        done_reps = state["actual"][idx]

        # Последний подход
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
            next_msg = (
                "Следующий шаг — отдых, затем *Тест максимума* 🏆"
                if cycle_day == 3
                else f"Следующий шаг — отдых, затем *День {cycle_day + 1}*"
            )
            status = "✅ Выполнено!" if completed else "💪 Сделал что смог!"

            await query.edit_message_text(
                f"{status}\n\n"
                f"*Результат:*\n`{sets_str}`\n\n"
                f"Сделано: *{total_actual}* / {total_planned} подтягиваний\n\n"
                f"{next_msg}",
                parse_mode="Markdown",
            )
            return

        # Таймер отдыха с обратным отсчётом
        rest = state["rest_seconds"]
        state["set_index"] = idx + 1
        state["processing"] = False
        while len(state["actual"]) <= idx + 1:
            state["actual"].append(sets[idx + 1])

        chat_id = query.message.chat_id
        msg_id = query.message.message_id
        bot = context.bot

        # Первое сообщение с таймером
        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=(
                f"✅ Подход {idx + 1} выполнен: *{done_reps}* повторений\n\n"
                f"⏱ Отдых *{rest // 60:02d}:{rest % 60:02d}*"
            ),
            parse_mode="Markdown",
        )

        # Обратный отсчёт — обновляем каждые 5 секунд
        for remaining in range(rest - 5, -1, -5):
            await asyncio.sleep(5)

            if not context.user_data.get("workout_state"):
                return

            mins = remaining // 60
            secs = remaining % 60
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=msg_id,
                    text=(
                        f"✅ Подход {idx + 1} выполнен: *{done_reps}* повторений\n\n"
                        f"⏱ Отдых *{mins:02d}:{secs:02d}*"
                    ),
                    parse_mode="Markdown",
                )
            except Exception:
                pass

        if not context.user_data.get("workout_state"):
            return

        await bot.edit_message_text(
            chat_id=chat_id,
            message_id=msg_id,
            text=f"✅ Подход {idx + 1} выполнен: *{done_reps}* повторений\n\n🔔 *Отдых закончился!*",
            parse_mode="Markdown",
        )
        await show_set_by_chat(bot, chat_id, context, idx + 1, sets, total_sets)
        return


async def show_set_by_chat(bot, chat_id, context, idx, sets, total_sets):
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


# ─────────────────────────── /plan ────────────────────────────

async def cmd_plan(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await get_user(user_id)
    if not user:
        await update.message.reply_text("Сначала запусти /start.", reply_markup=MAIN_KEYBOARD)
        return

    workouts = generate_cycle(user["current_max"])
    completed_days = await get_completed_days_this_cycle(user_id)
    current_day = user["cycle_day"]

    lines = [f"📋 *План цикла* (макс: {user['current_max']})\n"]
    for w in workouts:
        sets_str = "  ".join(str(s) for s in w.sets)
        rest_str = f"{w.rest_seconds // 60:02d}:{w.rest_seconds % 60:02d}"

        if w.day in completed_days:
            status = "✅"
        elif w.day == current_day and not user["is_rest_day"]:
            status = "▶️"
        else:
            status = "⬜"

        lines.append(f"{status} День {w.day}: `{sets_str}` — отдых {rest_str}")

    if current_day == 4 and not user["is_rest_day"]:
        test_status = "▶️"
    else:
        test_status = "⬜"
    lines.append(f"{test_status} Тест максимума 🏆")
    lines.append("\n_После дня 3 → день отдыха → Тест максимума_")

    await update.message.reply_text(
        "\n".join(lines),
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD,
    )


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

    max_history = stats.get("max_history", [])
    history_line = ""
    if len(max_history) > 1:
        history_str = " → ".join(str(m) for m in max_history[-6:])
        history_line = f"  • Динамика: *{history_str}*\n"

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


# ─────────────────────────── /help ────────────────────────────

async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📖 *Команды:*\n\n"
        "💪 *Тренировка* — начать тренировку дня\n"
        "📋 *План* — план цикла с галочками\n"
        "📊 *Прогресс* — статистика\n"
        "⚙️ *Настройки* — изменить максимум / сбросить цикл\n\n"
        "/cancel — отменить текущую тренировку\n"
        "/setmax — быстро изменить максимум\n"
        "/start — перезапуск",
        parse_mode="Markdown",
        reply_markup=MAIN_KEYBOARD,
    )


# ─────────────────────────── /setmax ──────────────────────────

async def cmd_setmax(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    user = await get_user(user_id)
    if not user:
        await update.message.reply_text("Сначала запусти /start.")
        return
    context.user_data["waiting_for_setmax"] = True
    context.user_data["old_max_setmax"] = user["current_max"]
    await update.message.reply_text(
        f"✏️ Текущий максимум: *{user['current_max']}*\n\nВведи новое число:",
        parse_mode="Markdown",
    )