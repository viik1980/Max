import logging
import os
import openai
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

from overpass_utils import find_nearby_places  # Убедись, что файл overpass_utils.py лежит рядом

# Простая память
context_history = []
MAX_TURNS = 6

# Загрузка токенов
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# Лог
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# Промт
try:
    with open("prompt.txt", "r", encoding="utf-8") as f:
        SYSTEM_PROMPT = f.read()
except FileNotFoundError:
    SYSTEM_PROMPT = "Ты — Макс. Диспетчер, помощник и навигатор по жизни в рейсе."

# GPT-ответ
async def ask_gpt(messages):
    try:
        return openai.ChatCompletion.acreate(model="gpt-4.5-preview", messages=messages)
    except Exception:
        return openai.ChatCompletion.acreate(model="gpt-3.5-turbo-1106", messages=messages)

# /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Здорова, я — Макс. Диспетчер, друг и напарник. Пиши или говори — помогу!\n\n"
        "Напиши `найди душ` или `найди магазин` (нужна геолокация).",
        parse_mode="Markdown"
    )

# Поиск по тексту (русский)
async def handle_find_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower().strip()
    if not text.startswith("найди"):
        return

    query = text.replace("найди", "").strip()
    tag_map = {
        "душ": ("amenity", "shower", "🚿 Душ"),
        "магазин": ("shop", "supermarket", "🛒 Магазин"),
        "аптека": ("amenity", "pharmacy", "💊 Аптека"),
        "парковка": ("amenity", "parking", "🅿️ Парковка"),
    }

    for key in tag_map:
        if key in query:
            tag_type, tag_value, label = tag_map[key]
            context.user_data["search_tag"] = (tag_type, tag_value, label)
            await update.message.reply_text("📍 Пришли мне геолокацию — и я найду " + label)
            return

    await update.message.reply_text("Я не знаю, как это искать. Примеры: `найди душ`, `найди магазин`.")

# Геолокация
async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if "search_tag" not in context.user_data:
        await update.message.reply_text("Сначала скажи, что искать. Например: `найди душ`")
        return

    lat = update.message.location.latitude
    lon = update.message.location.longitude
    tag_type, tag_value, label = context.user_data["search_tag"]
    results = find_nearby_places(lat, lon, tag_type, tag_value)

    if not results:
        await update.message.reply_text(f"❌ Не нашёл {label} поблизости.")
        return

    text = f"🔍 Найдено {label} поблизости:\n\n"
    for i, place in enumerate(results[:5], 1):
        name = place.get("tags", {}).get("name", "Без названия")
        dist = round(place["dist"], 1)
        text += f"{i}. {label} *{name}* — ~{dist} м\n"

    await update.message.reply_text(text, parse_mode="Markdown")

# Общение
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()

    if user_input.lower().startswith("найди"):
        await handle_find_query(update, context)
        return

    context_history.append({"role": "user", "content": user_input})
    messages = [{"role": "system", "content": SYSTEM_PROMPT}] + context_history[-MAX_TURNS:]
    response = await ask_gpt(messages)

    if response:
        assistant_reply = response.choices[0].message.content.strip()
        context_history.append({"role": "assistant", "content": assistant_reply})
        await update.message.reply_text(assistant_reply)
    else:
        await update.message.reply_text("❌ Ошибка при запросе к GPT.")

# Запуск
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
