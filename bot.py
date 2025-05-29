import logging
import os
import openai
import tempfile
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# === НАСТРОЙКА ===

# Включаем логирование
logging.basicConfig(format='%(asctime)s - %(levelname)s - %(message)s', level=logging.INFO)

# Telegram токен
TELEGRAM_TOKEN = os.getenv("max")
if not TELEGRAM_TOKEN:
    logging.error("TELEGRAM_TOKEN (max) not found in environment variables! Check Railway settings.")
    raise ValueError("TELEGRAM_TOKEN is required.")
logging.info(f"TELEGRAM_TOKEN loaded: {TELEGRAM_TOKEN[:5]}...")

# OpenAI ключ
OPENAI_API_KEY = os.getenv("ai")
if not OPENAI_API_KEY:
    logging.error("OPENAI_API_KEY (ai) not found in environment variables! Check Railway settings.")
    raise ValueError("OPENAI_API_KEY is required.")
openai.api_key = OPENAI_API_KEY
logging.info(f"OPENAI_API_KEY loaded: {OPENAI_API_KEY[:5]}...")  # Первые 5 символов для отладки

# === ОБРАБОТЧИКИ ===

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я — Макс. Говори, чем помочь? (Время: 22:14 CEST, 29 мая 2025)")

# Текстовые сообщения
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text
    logging.info(f"📩 Получено сообщение: {user_input}")

    try:
        logging.info("📤 Отправка запроса в OpenAI...")
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Ты — Макс. Опытный диспетчер с душой. Отвечай по-дружески, по делу."},
                {"role": "user", "content": user_input}
            ]
        )
        logging.info("📥 Ответ от OpenAI получен")
        reply = response.choices[0].message.content if response.choices else "⚠️ GPT не дал ответа."
    except Exception as e:
        logging.error(f"❌ Ошибка от GPT: {e}")
        reply = "⚠️ Макс не может ответить. GPT молчит или ошибка в запросе."
    await update.message.reply_text(reply)

# Голосовые сообщения
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        file = await update.message.voice.get_file()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".oga") as f:
            await file.download_to_drive(f.name)
            audio_path = f.name

        with open(audio_path, "rb") as audio_file:
            transcript = openai.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )
            user_text = transcript.text if transcript and "text" in transcript else ""

        if not user_text:
            await update.message.reply_text("🗣️ Не смог разобрать голос. Скажи ещё раз?")
            os.unlink(audio_path)
            return

        await update.message.reply_text(f"Ты сказал: {user_text}")

        logging.info("📤 Отправка текста из голосового в OpenAI...")
        response = openai.chat.completions.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Ты — Макс. Опытный диспетчер с заботой о водителях."},
                {"role": "user", "content": user_text},
            ]
        )
        logging.info("📥 Ответ от OpenAI получен")
        reply = response.choices[0].message.content if response.choices else "⚠️ GPT не дал ответа."
    except Exception as e:
        logging.error(f"❌ Ошибка при обработке голоса: {e}")
        reply = "⚠️ Макс не смог расшифровать голос или ответить. Попробуй ещё раз."
    finally:
        if 'audio_path' in locals():
            os.unlink(audio_path)
    await update.message.reply_text(reply)

# === ЗАПУСК ===

if __name__ == '__main__':
    try:
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        app.add_handler(MessageHandler(filters.VOICE, handle_voice))
        logging.info("🚀 Бот Макс запущен и слушает Telegram...")
        app.run_polling(allowed_updates=[])
    except Exception as e:
        logging.error(f"❌ Ошибка при запуске бота: {e}")
