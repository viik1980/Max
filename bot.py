import logging
import os
import openai
import tempfile
import time
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID = os.getenv("ASSISTANT_ID")  # ← Добавь в .env файл

# if not TELEGRAM_TOKEN or not OPENAI_API_KEY or not ASSISTANT_ID:
#   raise ValueError("Нужно задать TELEGRAM_TOKEN, OPENAI_API_KEY и ASSISTANT_ID в .env")

openai.api_key = OPENAI_API_KEY

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logging.info("[LOG] /start получена")
    await update.message.reply_text("Здорова, я — Макс. Диспетчер и друг. Пиши или говори — разберёмся!")

# Обработка текстовых сообщений через Assistant API
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    logging.info(f"[LOG] Получено сообщение: {user_input}")

    if not user_input:
        await update.message.reply_text("Напиши, чем могу помочь?")
        return

    try:
        # Создаём новый диалог (thread)
        thread = openai.beta.threads.create()

        # Отправляем сообщение в thread
        openai.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=user_input
        )

        # Запускаем ассистента
        run = openai.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=ASSISTANT_ID
        )

        # Ждём завершения
        while True:
            run_status = openai.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
            if run_status.status == "completed":
                break
            time.sleep(1)

        # Получаем ответ
        messages = openai.beta.threads.messages.list(thread_id=thread.id)
        for message in reversed(messages.data):
            if message.role == "assistant":
                reply = message.content[0].text.value
                await update.message.reply_text(reply)
                return

        await update.message.reply_text("⚠️ Макс не дал ответа.")
    except Exception as e:
        logging.error(f"[ERROR] GPT Assistant API ошибка: {e}")
        await update.message.reply_text("⚠️ Макс не может связаться с GPT. Ошибка.")

# Обработка голосовых сообщений (с расшифровкой и отправкой в ассистента)
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
            await update.message.reply_text("Не смог разобрать голос. Попробуй снова.")
            return

        await update.message.reply_text(f"Ты сказал: {user_text}")

        # Далее как с текстом
        thread = openai.beta.threads.create()
        openai.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=user_text
        )
        run = openai.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=ASSISTANT_ID
        )
        while True:
            run_status = openai.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)
            if run_status.status == "completed":
                break
            time.sleep(1)
        messages = openai.beta.threads.messages.list(thread_id=thread.id)
        for message in reversed(messages.data):
            if message.role == "assistant":
                reply = message.content[0].text.value
                await update.message.reply_text(reply)
                return

        await update.message.reply_text("⚠️ Макс не дал ответа.")
    except Exception as e:
        logging.error(f"[ERROR] Ошибка при голосе: {e}")
        await update.message.reply_text("⚠️ Не получилось обработать голос.")

# Запуск Telegram бота
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.run_polling()
