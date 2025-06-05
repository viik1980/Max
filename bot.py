import logging
import os
import openai
import tempfile
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

# Загрузка переменных окружения из .env файла
load_dotenv()

# Загрузка файла из папки knowledge
def load_knowledge(filename):
    try:
        with open(f"knowledge/{filename}", "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return ""

# Загрузка всех файлов из папки knowledge
def load_all_knowledge():
    knowledge_base = ""
    knowledge_dir = "knowledge"
    if os.path.exists(knowledge_dir):
        for filename in os.listdir(knowledge_dir):
            if filename.endswith(".txt"):
                knowledge_base += f"\n--- {filename} ---\n"
                knowledge_base += load_knowledge(filename)
                knowledge_base += "\n"
    return knowledge_base.strip()

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Переменные окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_TOKEN or not OPENAI_API_KEY:
    raise ValueError("Не установлены обязательные переменные окружения: TELEGRAM_TOKEN или OPENAI_API_KEY.")

openai.api_key = OPENAI_API_KEY

# Системный промт (из файла или по умолчанию)
try:
    with open("prompt.txt", "r", encoding="utf-8") as f:
        SYSTEM_PROMPT = f.read()
except FileNotFoundError:
    SYSTEM_PROMPT = "Ты — Макс. Опытный диспетчер. Отвечай по-дружески, с заботой, по делу и с уместным юмором."

# Загрузка базы знаний
KNOWLEDGE_BASE = load_all_knowledge()

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print("[LOG] /start получена")
    await update.message.reply_text("Здорова, я — Макс. Диспетчер и друг. Пиши или говори — разберёмся!")

# Обработка текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    print(f"[LOG] Получено сообщение: {user_input}")

    if not user_input:
        await update.message.reply_text("Напиши, чем могу помочь?")
        return

    try:
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "📚 Вот база знаний:\n" + KNOWLEDGE_BASE},
            {"role": "user", "content": user_input},
        ]

        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=messages
        )

        print(f"[LOG] GPT сырой ответ: {response}")
        reply = response.choices[0].message.content if response.choices else "GPT не дал ответа."
        await update.message.reply_text(reply)

    except Exception as e:
        print(f"[ERROR] GPT не сработал: {e}")
        await update.message.reply_text("⚠️ Макс не может связаться с GPT. Ошибка запроса.")

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

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": "📚 Вот база знаний:\n" + KNOWLEDGE_BASE},
            {"role": "user", "content": user_text},
        ]

        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=messages
        )

        print(f"[LOG] GPT голосовой ответ: {response}")
        reply = response.choices[0].message.content if response.choices else "GPT не дал ответа."
        await update.message.reply_text(reply)
    except Exception as e:
        logging.error(f"Ошибка при обработке голосового сообщения: {e}")
        await update.message.reply_text("⚠️ Макс не смог обработать голос. Проверь формат или попробуй позже.")

# Запуск бота
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.run_polling()
