import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
import requests

load_dotenv()

# Логирование
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# Получение переменных окружения
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
AI_API_URL = "http://localhost:5000/chat"  # или URL к развернутому Flask-серверу

# Загрузка системного промта
try:
    with open("prompt.txt", "r", encoding="utf-8") as f:
        SYSTEM_PROMPT = f.read()
except FileNotFoundError:
    SYSTEM_PROMPT = "Ты — Макс. Диспетчер, помощник и навигатор по жизни в рейсе."

# Загрузка знаний по ключевым словам
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

# Функция для получения ответа от Qwen
def get_qwen_response(query):
    kb_snippet = load_relevant_knowledge(query)
    full_prompt = SYSTEM_PROMPT + "\n\nПользователь: " + query + "\n\n📚 База знаний:\n" + kb_snippet

    try:
        response = requests.post(AI_API_URL, json={"query": full_prompt})
        return response.json().get("response", "Ошибка получения ответа.")
    except Exception as e:
        logging.error(f"Ошибка при вызове Qwen: {e}")
        return "⚠️ Не могу получить ответ."

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Здорова, я — Макс. Диспетчер, друг и напарник. Пиши — помогу.")

# Обработка текстовых сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    
    if not user_input:
        await update.message.reply_text("Напиши, чем могу помочь?")
        return

    reply = get_qwen_response(user_input)
    await update.message.reply_text(reply)

# Запуск бота
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
