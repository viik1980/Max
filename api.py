from flask import Flask, request, jsonify
from transformers import AutoTokenizer, AutoModelForCausalLM
import torch
import os

app = Flask(__name__)

# Путь к модели Qwen
MODEL_NAME = "Qwen/Qwen3"
tokenizer = None
model = None

# Инициализация модели
def load_model():
    global tokenizer, model
    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
    model = AutoModelForCausalLM.from_pretrained(MODEL_NAME).to("cuda" if torch.cuda.is_available() else "cpu")

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    query = data.get("query", "").strip()

    if not query:
        return jsonify({"error": "Пустой запрос"}), 400

    # Загрузка модели при первом запуске
    if tokenizer is None or model is None:
        load_model()

    # Формируем входной промт
    try:
        with open("prompt.txt", "r", encoding="utf-8") as f:
            system_prompt = f.read()
    except FileNotFoundError:
        system_prompt = "Ты — Макс. Диспетчер, помощник и навигатор по жизни в рейсе."

    full_prompt = f"{system_prompt}\n\nПользователь: {query}"

    # Генерация ответа
    inputs = tokenizer(full_prompt, return_tensors="pt").to(model.device)
    outputs = model.generate(**inputs, max_new_tokens=500, temperature=0.7)
    response = tokenizer.decode(outputs[0], skip_special_tokens=True)

    return jsonify({"response": response})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
