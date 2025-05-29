import logging
import os
import openai
import tempfile
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Ключи из переменных окружения
TELEGRAM_TOKEN = os.getenv("max")  # Переменная окружения для Telegram
OPENAI_API_KEY = os.getenv("ai")   # Переменная окружения для OpenAI

openai.api_key = OPENAI_API_KEY

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет, я Макс — твой дежурный диспетчер. Можешь писать или говорить голосом — разберусь 😉"
    )

# Обработка текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text
    logging.info(f"[LOG] Получено сообщение: {user_input}")

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Ты — Макс. Опытный диспетчер с душой. Отвечай по-дружески, по делу."},
                {"role": "user", "content": user_input}
            ]
        )
        reply = response.choices[0].message.content if response.choices else "GPT не дал ответа."
        await update.message.reply_text(reply)

    except Exception as e:
        logging.error(f"[ERROR] Ошибка при обращении к GPT: {e}")
        await update.message.reply_text("⚠️ Макс что-то не отвечает. Ошибка запроса к GPT.")

# Обработка голосовых сообщений
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        file = await update.message.voice.get_file()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".oga") as f:
            await file.download_to_drive(f.name)
            audio_path = f.name

        with open(audio_path, "rb") as audio_file:
            transcript = openai.Audio.transcribe("whisper-1", audio_file)
            user_text = transcript.get("text", "")

        if not user_text:
            await update.message.reply_text("Не смог разобрать голос. Попробуй сказать снова.")
            return

        await update.message.reply_text(f"Ты сказал: {user_text}")

        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Ты — Макс. Опытный диспетчер с душой. Отвечай чётко, по-дружески, с заботой о водителе."},
                {"role": "user", "content": user_text},
            ]
        )
        reply = response.choices[0].message.content if response.choices else "GPT не дал ответа. Попробуй ещё раз."
        await update.message.reply_text(reply)

    except Exception as e:
        logging.error(f"[ERROR] Ошибка при обработке голосового сообщения: {e}")
        await update.message.reply_text("⚠️ Макс не смог обработать голос. Проверь формат или попробуй позже.")

# Запуск бота
if __name__ == '__main__':
    if not TELEGRAM_TOKEN or not OPENAI_API_KEY:
        logging.error("❌ Отсутствует токен. Проверь переменные окружения 'max' и 'ai'.")
        exit(1)

    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))

    logging.info("🚀 Бот Макс запущен!")
    app.run_polling()
