import logging
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
import requests

# Память между сообщениями (примитивная, можно позже заменить на Redis или файл)
context_history = []
MAX_TURNS = 6  # сколько ходов помнить (user + assistant)

# Загрузка переменных окружения
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
QWEN_API_KEY = os.getenv("QWEN_API_KEY")

# Настройка логгирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# URL для обращения к Qwen API
QWEN_API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation" 

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

# Qwen-запрос
async def ask_qwen(prompt):
    headers = {
        "Authorization": f"Bearer {QWEN_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": "qwen3",
        "input": {
            "prompt": prompt
        },
        "parameters": {
            "max_tokens": 500,
            "temperature": 0.7
        }
    }

    try:
        response = requests.post(QWEN_API_URL, json=data, headers=headers)
        result = response.json()

        if response.status_code == 200 and 'output' in result and 'text' in result['output']:
            return result['output']['text'].strip()
        else:
            logging.error(f"Ошибка при запросе к Qwen: {result}")
            return None
    except Exception as e:
        logging.error(f"Сервер не отвечает: {e}")
        return None

# Команда /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Здорова, я — Макс. Диспетчер, друг и напарник. Пиши — помогу.")

# Обработка сообщений
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    if not user_input:
        await update.message.reply_text("Чем могу помочь?")
        return

    # Добавляем реплику пользователя в историю
    context_history.append({"role": "user", "content": user_input})

    # Формируем сообщение для Qwen
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    kb_snippet = load_relevant_knowledge(user_input)
    if kb_snippet:
        messages.append({"role": "system", "content": "📚 База знаний:\n" + kb_snippet})

    # Добавляем последние ходы
    messages += context_history[-MAX_TURNS:]

    # Формируем текстовый промт для Qwen
    qwen_prompt = "\n\n".join([f"{msg['role']}: {msg['content']}" for msg in messages])

    # Получаем ответ от Qwen
    reply = await ask_qwen(qwen_prompt)

    # Сохраняем и отправляем ответ
    if reply:
        context_history.append({"role": "assistant", "content": reply})
        await update.message.reply_text(reply)
    else:
        await update.message.reply_text("❌ Ошибка при запросе к Qwen. Проверь токен или попробуй позже.")

# Запуск бота
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.run_polling()
