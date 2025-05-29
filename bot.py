import logging
import os
import openai
import tempfile
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

TELEGRAM_TOKEN = os.getenv("max")
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN is required.")
OPENAI_API_KEY = os.getenv("ai")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY is required.")
openai.api_key = OPENAI_API_KEY

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я — Макс. Говори, чем помочь? (Время: 22:30 CEST, 29 мая 2025)")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text
    try:
        response = openai.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": user_input}])
        reply = response.choices[0].message.content
    except Exception as e:
        reply = "Ошибка связи с GPT."
    await update.message.reply_text(reply)

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling(allowed_updates=[])
