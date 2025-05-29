# bot.py — Макс: Telegram + GPT-4o + голос (через Railway)

import logging
import os
import openai
import tempfile
import requests
import os
from telegram import Update, Voice, constants
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes

# Настройка логов
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Ключи из переменных среды
TELEGRAM_TOKEN = os.getenv("max")
OPENAI_API_KEY = os.getenv("ai")
if not OPENAI_API_KEY:
    raise ValueError("OpenAI API Key 'ai' not found in environment variables!")
openai.api_key = OPENAI_API_KEY
print(f"OpenAI API Key loaded: {openai.api_key}")

# Обработка команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Здорова, я — Макс. Готов к рейсу. Пиши или говори — разберёмся!")

# Обработка текста
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Ты дружелюбный и знающий помощник-диспетчер Макс, общаешься по-дружески, но по делу."},
                {"role": "user", "content": user_input},
            ]
        )
        reply = response.choices[0].message.content
    except Exception as e:
        print(f"Error with OpenAI: {e}")
        reply = "Ошибка связи с GPT, попробуй позже."
    await update.message.reply_text(reply)

# Обработка голосовых сообщений
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    file = await update.message.voice.get_file()
    with tempfile.NamedTemporaryFile(delete=False, suffix=".oga") as f:
        await file.download_to_drive(f.name)
        audio_path = f.name

    try:
        with open(audio_path, "rb") as audio_file:
            transcript = openai.Audio.transcribe("whisper-1", audio_file)
            user_text = transcript["text"]
        await update.message.reply_text(f"Ты сказал: {user_text}")

        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "Ты дружелюбный и знающий помощник-диспетчер Макс, общаешься по-дружески, но по делу."},
                {"role": "user", "content": user_text},
            ]
        )
        reply = response.choices[0].message.content
    except Exception as e:
        print(f"Error with OpenAI: {e}")
        reply = "Ошибка обработки голоса или GPT."
    await update.message.reply_text(reply)
    os.unlink(audio_path)  # Удаляем временный файл

# Запуск бота
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.run_polling()
