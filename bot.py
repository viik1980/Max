import logging
import os
import openai
import tempfile
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
from overpass_utils import query_overpass, parse_places

# Простая память между сообщениями
context_history = []
MAX_TURNS = 6

# Загрузка .env
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
openai.api_key = OPENAI_API_KEY

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Загрузка промта
try:
    with open("prompt.txt", "r", encoding="utf-8") as f:
        SYSTEM_PROMPT = f.read()
except FileNotFoundError:
    SYSTEM_PROMPT = "Ты — Макс. Диспетчер, помощник и навигатор по жизни в рейсе."

# Загрузка базы знаний по ключевым словам
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

# GPT-запрос
async def ask_gpt(messages):
    try:
        return openai.ChatCompletion.create(model="gpt-4.5-preview", messages=messages)
    except Exception as e:
        logging.warning(f"GPT-4.5-preview недоступен, fallback: {e}")
        try:
            return openai.ChatCompletion.create(model="gpt-3.5-turbo-1106", messages=messages)
        except Exception as e2:
            logging.error(f"GPT-3.5 тоже не сработал: {e2}")
            return None

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Здорова, я — Макс. Диспетчер, друг и напарник. Пиши, говори или отправляй координаты — разберёмся!")

# Обработка текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    if not user_input:
        await update.message.reply_text("Чем могу помочь?")
        return

    lowered = user_input.lower()

    # Генерация изображения
    if any(keyword in lowered for keyword in ["нарисуй", "покажи", "сгенерируй", "изображение", "картинку", "картина"]):
        try:
            image_response = openai.Image.create(prompt=user_input, n=1, size="512x512")
            image_url = image_response['data'][0]['url']
            await update.message.reply_photo(photo=image_url, caption="🖼️ Вот как это может выглядеть:")
            return
        except Exception as e:
            logging.error(f"Ошибка генерации изображения: {e}")
            await update.message.reply_text("❌ Не удалось сгенерировать изображение. Попробуй позже.")
            return

    # Контекст
    context_history.append({"role": "user", "content": user_input})
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    kb_snippet = load_relevant_knowledge(user_input)
    if kb_snippet:
        messages.append({"role": "system", "content": "📚 База знаний:\n" + kb_snippet})
    messages += context_history[-MAX_TURNS:]

    response = await ask_gpt(messages)
    if response:
        assistant_reply = response.choices[0].message.content.strip()
        context_history.append({"role": "assistant", "content": assistant_reply})
        await update.message.reply_text(assistant_reply)
    else:
        await update.message.reply_text("❌ Ошибка при запросе к GPT. Попробуй позже.")

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
            await update.message.reply_text("🎧 Не смог разобрать голос. Попробуй снова.")
            return

        await update.message.reply_text(f"Ты сказал: {user_text}")

        context_history.append({"role": "user", "content": user_text})
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        kb_snippet = load_relevant_knowledge(user_text)
        if kb_snippet:
            messages.append({"role": "system", "content": "📚 База знаний:\n" + kb_snippet})
        messages += context_history[-MAX_TURNS:]

        response = await ask_gpt(messages)
        if response:
            assistant_reply = response.choices[0].message.content.strip()
            context_history.append({"role": "assistant", "content": assistant_reply})
            await update.message.reply_text(assistant_reply)
        else:
            await update.message.reply_text("❌ Ошибка при запросе к GPT. Попробуй позже.")

    except Exception as e:
        logging.error(f"[ERROR] Голосовая ошибка: {e}")
        await update.message.reply_text("⚠️ Не смог обработать голос. Возможно, проблема с форматом.")

# Обработка геолокации
async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lat = update.message.location.latitude
    lon = update.message.location.longitude
    await update.message.reply_text("📍 Получил координаты. Ищу рядом магазины, парковки и аптеки...")

    data = await query_overpass(lat, lon)
    if data:
        places = parse_places(data)
        if places:
            await update.message.reply_text("\n\n".join(places))
        else:
            await update.message.reply_text("❗ Ничего не нашёл поблизости.")
    else:
        await update.message.reply_text("⚠️ Не удалось получить данные от Overpass API.")

# Запуск бота
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    app.run_polling()
