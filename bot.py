"""
bot.py — точка входа Telegram бота
"""

import os
import asyncio
import sys
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from database import init_db
from handlers import (
    cmd_start,
    cmd_workout,
    cmd_progress,
    cmd_plan,
    cmd_help,
    handle_text,
    handle_callback,
)

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден. Создай файл .env с BOT_TOKEN=твой_токен")


def main():
    # Инициализация базы данных (синхронно до запуска PTB)
    asyncio.get_event_loop().run_until_complete(init_db())
    print("✅ База данных готова")

    # Создаём приложение
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    # Регистрируем обработчики
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("workout", cmd_workout))
    app.add_handler(CommandHandler("progress", cmd_progress))
    app.add_handler(CommandHandler("plan", cmd_plan))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    print("🤖 Бот запущен...")

    # PTB сам управляет своим event loop
    webhook_url = os.getenv("WEBHOOK_URL")

    if webhook_url:
        port = int(os.getenv("PORT", 8443))
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            webhook_url=f"{webhook_url}/webhook",
        )
    else:
        app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    main()