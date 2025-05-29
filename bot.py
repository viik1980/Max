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
    raise ValueError("TELEGRAM_TOKEN (max) not found in environment variables! Please set it in Railway.")

# OpenAI ключ
OPENAI_API_KEY = os.getenv("ai")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY (ai) not found in environment variables! Please set it in Railway.")
openai.api_key = OPENAI_API_KEY
logging.info(f"OpenAI API Key loaded: {openai.api_key[:5]}...")  # Логируем первые 5 символов для безопасности

# === ОБРАБОТЧИКИ ===

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я — Макс. Говори, чем помочь?")

# Текстовые сообщения
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text
    logging.info(f"📩 Получено сообщение: {user_input}")

    try:
        logging.info("📤 Отправка запроса в OpenAI...")
        response = openai.chat.completions.create(  # Исправлен синтаксис для openai>=1.0.0
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Ты — Макс. Опытный диспетчер с душой. Отвечай по-дружески, по делу."},
                {"role": "user", "content": user_input}
            ]
        )
        logging.info("📥 Ответ от OpenAI получен")

        if response and response.choices and len(response.choices) > 0:
            reply = response.choices[0].message.content
        else:
            reply = "⚠️ GPT не дал ответа."

        await update.message.reply_text(reply)

    except Exception as e:
        logging.error(f"❌ Ошибка от GPT: {e}")
        await update.message.reply_text("⚠️ Макс не может ответить. GPT молчит или ошибка в запросе.")

# Голосовые сообщения
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        file = await update.message.voice.get_file()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".oga") as f:
            await file.download_to_drive(f.name)
            audio_path = f.name

        with open(audio_path, "rb") as audio_file:
            transcript = openai.audio.transcriptions.create(  # Исправлен синтаксис для openai>=1.0.0
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

        if response and response.choices and len(response.choices) > 0:
            reply = response.choices[0].message.content
        else:
            reply = "⚠️ GPT не дал ответа."

        await update.message.reply_text(reply)

    except Exception as e:
        logging.error(f"❌ Ошибка при обработке голоса: {e}")
        await update.message.reply_text("⚠️ Макс не смог расшифровать голос или ответить. Попробуй ещё раз.")
    finally:
        if 'audio_path' in locals():
            os.unlink(audio_path)  # Удаляем временный файл даже при ошибке

# === ЗАПУСК ===

if __name__ == '__main__':
    if not TELEGRAM_TOKEN:
        logging.error("Бот не запустился: TELEGRAM_TOKEN не установлен.")
    else:
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        app.add_handler(MessageHandler(filters.VOICE, handle_voice))
        logging.info("🚀 Бот Макс запущен и слушает Telegram...")
        app.run_webhook(  # Переключение на вебхуки вместо polling
            listen="0.0.0.0",
            port=8443,
            url_path="webhook",
            webhook_url="https://your-railway-app.com/webhook"  # Замени на реальный URL твоего приложения
        )
