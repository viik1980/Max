import logging
import os
import openai
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
from datetime import datetime
from logic.route_calc import calculate_eta

# Простейшая память
context_history = []
MAX_TURNS = 6

# Загрузка .env
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# Логирование
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Промт Макса
try:
    with open("prompt.txt", "r", encoding="utf-8") as f:
        SYSTEM_PROMPT = f.read()
except FileNotFoundError:
    SYSTEM_PROMPT = "Ты — Макс. Диспетчер, помощник и напарник дальнобойщика. Всё по-человечески."

# База знаний по ключевым словам
def load_relevant_knowledge(user_input: str) -> str:
    keywords_map = {
        "отдых": "Rezim_RTO.md",
        "пауз": "Rezim_RTO.md",
        "смен": "Rezim_RTO.md",
        "тахограф": "4_tahograf_i_karty.md",
        "карта": "4_tahograf_i_karty.md",
        "поезд": "ferry_routes.md",
        "паром": "ferry_routes.md",
        "цмр": "CMR.md",
        "документ": "CMR.md",
        "комфорт": "11_komfort_i_byt.md",
        "питание": "12_pitanie_i_energiya.md"
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
                    texts.append(f"📘 {filename}:\n{content}\n")
    return "\n".join(texts) or ""

# Обращение к GPT
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

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Здорова, я — Макс. Диспетчер, друг и навигатор по рейсу. Пиши — вместе разберёмся!")

# Обработка сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    if not user_input:
        await update.message.reply_text("Чем могу помочь?")
        return

    lowered = user_input.lower()
    logging.info(f"Получено сообщение: {lowered}")

    # Проверка на расчёт маршрута
    keywords = ["расчитай", "маршрут", "загрузка", "выгрузка", "км", "время"]
    if any(keyword in lowered for keyword in keywords):
        logging.info(f"Ключевые слова найдены: {keywords}")
        try:
            segments = [
                {"type": "drive", "distance_km": 240},
                {"type": "wait", "duration_min": 60, "note": "Загрузка"},
                {"type": "drive", "distance_km": 600},
                {"type": "pause", "duration_min": 30, "note": "Заправка"},
                {"type": "drive", "distance_km": 1050}
            ]
            start_time = datetime.strptime("2025-06-06 06:00", "%Y-%m-%d %H:%M")
            result, total_km = calculate_eta(start_time, segments)

            reply_lines = ["🛣️ График маршрута:\n"]
            for e in result:
                reply_lines.append(f"🕒 {e['start'].strftime('%d.%m %H:%M')} → {e['end'].strftime('%H:%M')} | {e['action']}")
            reply_lines.append(f"\n📏 Всего: {total_km} км")

            await update.message.reply_text("\n".join(reply_lines))
            return
        except Exception as e:
            logging.error(f"Ошибка расчёта маршрута: {e}")
            await update.message.reply_text("❌ Ошибка при расчёте маршрута.")
            return
    else:
        logging.info(f"Ключевые слова не найдены: {keywords}")

    # GPT-ответ
    context_history.append({"role": "user", "content": user_input})
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    kb_snippet = load_relevant_knowledge(user_input)
    if kb_snippet:
        messages.append({"role": "system", "content": "📚 База знаний:\n" + kb_snippet})
    messages += context_history[-MAX_TURNS:]

    response = await ask_gpt(messages)

    if response:
        reply = response.choices[0].message.content.strip()
        context_history.append({"role": "assistant", "content": reply})
        await update.message.reply_text(reply)
    else:
        await update.message.reply_text("❌ Макс не смог получить ответ. Попробуй позже.")
# Запуск
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
