import logging
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
import requests

load_dotenv()

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Переменные окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
AI_PROVIDER = os.getenv("AI_PROVIDER", "max")  # По умолчанию Max
MAX_API_URL = os.getenv("MAX_API_URL", "https://max-production-c297.up.railway.app/chat ") 

# Функция для получения ответа от Макса
def get_max_response(query):
    try:
        response = requests.post(MAX_API_URL, json={"query": query})
        return response.json().get("response", "Ошибка получения ответа.")
    except Exception as e:
        logging.error(f"Ошибка при вызове Макса: {e}")
        return "⚠️ Не могу получить ответ."

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Здорова, я — Макс. Диспетчер и друг. Пиши или говори — разберёмся!")

# Обработка текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    
    if not user_input:
        await update.message.reply_text("Напиши, чем могу помочь?")
        return

    reply = get_max_response(user_input)
    await update.message.reply_text(reply)

# Запуск бота
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
