import os
import time
import httpx
import openai
import logging
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID = os.getenv("ASSISTANT_ID")

if not TELEGRAM_TOKEN or not OPENAI_API_KEY or not ASSISTANT_ID:
    raise ValueError("Нужно задать TELEGRAM_TOKEN, OPENAI_API_KEY и ASSISTANT_ID в .env")

openai.api_key = OPENAI_API_KEY

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
user_threads = {}  # Хранит thread_id для каждого пользователя

def get_updates(offset=None):
    try:
        res = httpx.get(f"{TELEGRAM_API_URL}/getUpdates", params={"timeout": 30, "offset": offset}, timeout=60)
        res.raise_for_status()
        return res.json().get("result", [])
    except Exception as e:
        logger.error(f"[ERROR] get_updates: {e}")
        return []

def send_message(chat_id, text):
    try:
        httpx.post(f"{TELEGRAM_API_URL}/sendMessage", json={"chat_id": chat_id, "text": text}, timeout=30)
        logger.info(f"[SEND] Сообщение отправлено => {chat_id}")
    except Exception as e:
        logger.error(f"[ERROR] send_message: {e}")

def ask_assistant(user_id, message_text):
    try:
        # Создаём thread, если нет
        thread_id = user_threads.get(user_id)
        if not thread_id:
            thread = openai.beta.threads.create()
            thread_id = thread.id
            user_threads[user_id] = thread_id
            logger.info(f"[THREAD] Создан новый thread для {user_id}: {thread_id}")

        # Добавляем сообщение от пользователя
        openai.beta.threads.messages.create(
            thread_id=thread_id,
            role="user",
            content=message_text
        )

        # Запускаем ассистента
        run = openai.beta.threads.runs.create(
            thread_id=thread_id,
            assistant_id=ASSISTANT_ID
        )

        # Ждём завершения
        while True:
            run_status = openai.beta.threads.runs.retrieve(thread_id=thread_id, run_id=run.id)
            if run_status.status == "completed":
                break
            elif run_status.status == "failed":
                return "❌ Ошибка при запуске ассистента."
            time.sleep(1)

        # Получаем ответ
        messages = openai.beta.threads.messages.list(thread_id=thread_id)
        for msg in reversed(messages.data):
            if msg.role == "assistant":
                return msg.content[0].text.value

        return "🤖 Ассистент не дал ответ."
    except Exception as e:
        logger.error(f"[ERROR] GPT Assistant API: {e}")
        return "❌ Ошибка при обращении к ассистенту."

def main():
    logger.info("Бот запущен. Ожидаю сообщения...")
    offset = None

    while True:
        updates = get_updates(offset)
        for update in updates:
            offset = update["update_id"] + 1

            if "message" in update and "text" in update["message"]:
                chat_id = update["message"]["chat"]["id"]
                user_id = update["message"]["from"]["id"]
                text = update["message"]["text"]

                logger.info(f"[RECV] {text} от {user_id}")
                reply = ask_assistant(user_id, text)
                send_message(chat_id, reply)

        time.sleep(1)

if __name__ == "__main__":
    main()
