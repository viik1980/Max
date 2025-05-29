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
TELEGRAM_TOKEN = os.getenv("max")  # Или временно вставь прямо сюда
# TELEGRAM_TOKEN = "ваш_telegram_token"

# OpenAI ключ
openai.api_key = "ai"  # Временно вставьте сюда

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
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Ты — Макс. Опытный диспетчер с душой. Отвечай по-дружески, по делу."},
                {"role": "user", "content": user_input}
            ]
        )
        logging.info("📥 Ответ от OpenAI получен")

        if response and "choices" in response and len(response["choices"]) > 0:
            reply = response["choices"][0]["message"]["content"]
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
            transcript = openai.Audio.transcribe("whisper-1", audio_file)
            user_text = transcript.get("text", "")

        if not user_text:
            await update.message.reply_text("🗣️ Не смог разобрать голос. Скажи ещё раз?")
            return

        await update.message.reply_text(f"Ты сказал: {user_text}")

        logging.info("📤 Отправка текста из голосового в OpenAI...")
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Ты — Макс. Опытный диспетчер с заботой о водителях."},
                {"role": "user", "content": user_text},
            ]
        )
        logging.info("📥 Ответ от OpenAI получен")

        if response and "choices" in response and len(response["choices"]) > 0:
            reply = response["choices"][0]["message"]["content"]
        else:
            reply = "⚠️ GPT не дал ответа."

        await update.message.reply_text(reply)

    except Exception as e:
        logging.error(f"❌ Ошибка при обработке голоса: {e}")
        await update.message.reply_text("⚠️ Макс не смог расшифровать голос или ответить. Попробуй ещё раз.")

# === ЗАПУСК ===

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    logging.info("🚀 Бот Макс запущен и слушает Telegram...")
    app.run_polling()
