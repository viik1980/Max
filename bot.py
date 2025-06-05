import os
import time
import httpx
import logging
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID = os.getenv("ASSISTANT_ID")

if not TELEGRAM_TOKEN or not OPENAI_API_KEY or not ASSISTANT_ID:
    raise ValueError("Нужно задать TELEGRAM_TOKEN, OPENAI_API_KEY и ASSISTANT_ID")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()

TELEGRAM_API_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"

user_threads = {}  # user_id -> thread_id mapping

HEADERS = {
    "Authorization": f"Bearer {OPENAI_API_KEY}",
    "Content-Type": "application/json"
}

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

def create_thread():
    url = "https://api.openai.com/v1/beta/threads"
    try:
        response = httpx.post(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        return response.json()["id"]
    except Exception as e:
        logger.error(f"[ERROR] create_thread: {e}")
        return None

def add_user_message(thread_id, content):
    url = f"https://api.openai.com/v1/beta/threads/{thread_id}/messages"
    data = {
        "role": "user",
        "content": content
    }
    try:
        response = httpx.post(url, headers=HEADERS, json=data, timeout=30)
        response.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"[ERROR] add_user_message: {e}")
        return False

def run_assistant(thread_id):
    url = f"https://api.openai.com/v1/beta/threads/{thread_id}/runs"
    data = {
        "assistant_id": ASSISTANT_ID
    }
    try:
        response = httpx.post(url, headers=HEADERS, json=data, timeout=30)
        response.raise_for_status()
        return response.json()["id"]
    except Exception as e:
        logger.error(f"[ERROR] run_assistant: {e}")
        return None

def get_run_status(thread_id, run_id):
    url = f"https://api.openai.com/v1/beta/threads/{thread_id}/runs/{run_id}"
    try:
        response = httpx.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"[ERROR] get_run_status: {e}")
        return None

def get_messages(thread_id):
    url = f"https://api.openai.com/v1/beta/threads/{thread_id}/messages"
    try:
        response = httpx.get(url, headers=HEADERS, timeout=30)
        response.raise_for_status()
        return response.json().get("data", [])
    except Exception as e:
        logger.error(f"[ERROR] get_messages: {e}")
        return []

def ask_assistant(user_id, message_text):
    try:
        thread_id = user_threads.get(user_id)
        if not thread_id:
            thread_id = create_thread()
            if not thread_id:
                return "❌ Не удалось создать диалог с ассистентом."
            user_threads[user_id] = thread_id
            logger.info(f"[THREAD] Создан новый thread для {user_id}: {thread_id}")

        if not add_user_message(thread_id, message_text):
            return "❌ Ошибка при добавлении сообщения."

        run_id = run_assistant(thread_id)
        if not run_id:
            return "❌ Ошибка при запуске ассистента."

        # Ждем пока run завершится
        for _ in range(30):  # максимум 30 попыток по 1 секунде = 30 секунд
            status_data = get_run_status(thread_id, run_id)
            if not status_data:
                break
            status = status_data.get("status")
            if status == "completed":
                break
            elif status == "failed":
                return "❌ Ассистент завершился с ошибкой."
            time.sleep(1)
        else:
            return "❌ Таймаут ожидания ответа ассистента."

        # Получаем последние сообщения
        messages = get_messages(thread_id)
        # Ищем последнее сообщение от ассистента
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                # Возвращаем текст ответа
                content = msg.get("content")
                # content — это список, берем первый элемент и его текст
                if isinstance(content, list) and len(content) > 0:
                    return content[0].get("text", "🤖 Ответ пуст.")
                return "🤖 Ответ пуст."
        return "🤖 Ассистент не дал ответ."
    except Exception as e:
        logger.error(f"[ERROR] ask_assistant: {e}")
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
