import os
import time
import httpx
import logging
from dotenv import load_dotenv
import openai

# Загрузка переменных из .env
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
ASSISTANT_ID = os.getenv("ASSISTANT_ID")

if not TELEGRAM_TOKEN or not OPENAI_API_KEY or not ASSISTANT_ID:
    raise ValueError("Нужно задать TELEGRAM_TOKEN, OPENAI_API_KEY и ASSISTANT_ID в .env")

openai.api_key = OPENAI_API_KEY
logging.basicConfig(level=logging.INFO)

BASE_URL = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}"
LAST_UPDATE_ID = None

def send_message(chat_id, text):
    response = httpx.post(f"{BASE_URL}/sendMessage", json={
        "chat_id": chat_id,
        "text": text
    })
    logging.info(f"[SEND] {text} => {chat_id}")
    return response

def get_updates():
    global LAST_UPDATE_ID
    params = {"timeout": 30}
    if LAST_UPDATE_ID:
        params["offset"] = LAST_UPDATE_ID + 1
    response = httpx.get(f"{BASE_URL}/getUpdates", params=params)
    return response.json()["result"]

def ask_openai(message_text):
    try:
        thread = openai.beta.threads.create()
        openai.beta.threads.messages.create(
            thread_id=thread.id,
            role="user",
            content=message_text
        )
        run = openai.beta.threads.runs.create(
            thread_id=thread.id,
            assistant_id=ASSISTANT_ID
        )

        # Подождём выполнения
        while True:
            run = openai.beta.threads.runs.retrieve(
                thread_id=thread.id, run_id=run.id
            )
            if run.status == "completed":
                break
            time.sleep(1)

        # Получаем ответ
        messages = openai.beta.threads.messages.list(thread_id=thread.id)
        for m in reversed(messages.data):
            if m.role == "assistant":
                return m.content[0].text.value

        return "Я что-то не понял 🤔"
    except Exception as e:
        logging.error(f"[ERROR] GPT Assistant API ошибка: {e}")
        return "Произошла ошибка при обращении к ИИ 🤖"

def main():
    global LAST_UPDATE_ID
    logging.info("Бот запущен. Ожидаю сообщения...")

    while True:
        try:
            updates = get_updates()
            for update in updates:
                LAST_UPDATE_ID = update["update_id"]
                if "message" in update:
                    chat_id = update["message"]["chat"]["id"]
                    text = update["message"].get("text", "")
                    logging.info(f"[LOG] Получено сообщение: {text}")
                    if text == "/start":
                        send_message(chat_id, "Привет! Я Дежурный Макс 👋 Готов помочь. Просто напиши мне.")
                    elif text:
                        reply = ask_openai(text)
                        send_message(chat_id, reply)
        except Exception as e:
            logging.error(f"[ERROR] {e}")
            time.sleep(3)

if __name__ == "__main__":
    main()
