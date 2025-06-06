
import logging
import os
import openai
import tempfile
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
# Память между сообщениями (примитивная, можно позже заменить на Redis или файл)
context_history = []
MAX_TURNS = 4  # сколько ходов помнить (user + assistant)


load_dotenv()
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

try:
    with open("prompt.txt", "r", encoding="utf-8") as f:
        SYSTEM_PROMPT = f.read()
except FileNotFoundError:
    SYSTEM_PROMPT = "Ты — Макс. Диспетчер, помощник и навигатор по жизни в рейсе."

def load_relevant_knowledge(user_input: str) -> str:
    keywords_map = {
        "отдых": "rezhim_truda.md",
        "пауз": "rezhim_truda.md",
        "смен": "rezhim_truda.md",
        "тахограф": "tahograf.md",
        "карта": "tahograf.md",
        "ECTP": "ectp.md",
        "поезд": "ferry_routes.md",
        "паром": "ferry_routes.md",
        "цмр": "cmr.md",
        "документ": "cmr.md",
        "катящееся шоссе": "katyaschee_shosse.md",
        "железн": "katyaschee_shosse.md"
    }

    selected_files = set()
    lowered = user_input.lower()
    for keyword, filename in keywords_map.items():
        if keyword in lowered:
            selected_files.add(filename)

    texts = []
    for filename in sorted(selected_files):
        path = os.path.join("knowledge", filename)
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    texts.append(
    f"📘 {filename}:\n"
    f"{content}\n"
)

    return "\n".join(texts) or ""

async def ask_gpt(messages):
    try:
        return openai.ChatCompletion.create(model="gpt-4o", messages=messages)
    except Exception as e:
        logging.warning(f"GPT-4o недоступен, fallback: {e}")
        try:
            return openai.ChatCompletion.create(model="gpt-3.5-turbo-1106", messages=messages)
        except Exception as e2:
            logging.error(f"GPT-3.5 тоже не сработал: {e2}")
            return None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Здорова, я — Макс. Диспетчер, друг и напарник. Пиши — помогу.")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    if not user_input:
        await update.message.reply_text("Чем могу помочь?")
        return

    # Добавляем в историю
context_history.append({"role": "user", "content": user_input})

# Формируем полное сообщение с историей
messages = [{"role": "system", "content": SYSTEM_PROMPT}]
kb_snippet = load_relevant_knowledge(user_input)
if kb_snippet:
    messages.append({"role": "system", "content": "📚 База знаний:\n" + kb_snippet})

# Вставляем последние реплики из памяти
messages += context_history[-MAX_TURNS:]

# GPT отвечает
response = await ask_gpt(messages)

# Сохраняем ответ в память
if response:
    assistant_reply = response.choices[0].message.content.strip()
    context_history.append({"role": "assistant", "content": assistant_reply})
     await update.message.reply_text("⚠️ Макс не может ответить. Попробуй позже.")

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
