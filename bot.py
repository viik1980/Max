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

# URL для обращения к Qwen API через OpenRouter
QWEN_API_URL = "https://api.openrouter.ai/v1/chat/completions" 

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
async
