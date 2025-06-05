import os
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
import requests

# Загрузка переменных окружения
load_dotenv()

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Получение переменных
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
AI_PROVIDER = os.getenv("AI_PROVIDER", "gpt")  # По умолчанию GPT

# URL, куда обращается бот за ответом от меня
AI_API_URL = "https://your-suvvy-api-url.com/chat" 

# Функция для отправки запроса ко мне
def get_suvvy_response(query):
    try:
        response = requests.post(AI_API_URL, json={"query": query})
        return response.json().get("response", "Ошибка получения ответа.")
    except Exception as e:
        logging.error(f"Ошибка при вызове Suvvy.ai: {e}")
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

    if AI_PROVIDER == "suvvy":
        reply = get_suvvy_response(user_input)
    else:
        reply = "Не поддерживается пока что."

    await update.message.reply_text(reply)

# Запуск бота
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
