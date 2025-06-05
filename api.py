from flask import Flask, request, jsonify
import os
from dotenv import load_dotenv

app = Flask(__name__)
load_dotenv()

# Получаем URL, куда будем отправлять запросы
MAX_API_URL = os.getenv("MAX_API_URL")

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_query = data.get("query", "")

    if not user_query:
        return jsonify({"error": "Нет сообщения"}), 400

    try:
        # Отправляем запрос к Максу (к тебе)
        response = requests.post(MAX_API_URL, json={"query": user_query})
        max_response = response.json().get("response", "Ошибка получения ответа.")
        return jsonify({"response": max_response})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
