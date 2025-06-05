from flask import Flask, request, jsonify
import os
from dotenv import load_dotenv

app = Flask(__name__)
load_dotenv()

# Функция для обработки запросов
def process_query(query):
    query = query.lower()
    
    # Базы знаний
    rto_rules = ""
    if os.path.exists("knowledge/3_rezhim_truda_otdykha.txt"):
        with open("knowledge/3_rezhim_truda_otdykha.txt", "r", encoding="utf-8") as f:
            rto_rules = f.read()

    # Логика обработки запросов
    if "рассчитай" in query or "расчёт" in query or "сколько времени нужно" in query:
        return calculate_route(query)

    elif "ежедневный отдых" in query:
        return "Ежедневный отдых должен составлять минимум 11 часов согласно статье 8(2)."

    elif "сокращённый отдых" in query:
        return "Сокращённый ежедневный отдых может быть до 9 часов, но не более трёх раз между двумя еженедельными отдыхами."

    elif "перерыв" in query:
        return "Обязательный перерыв — 45 минут после 4,5 часа непрерывного вождения. Можно разделить на две части: 15 мин + 30 мин."

    elif "продление" in query or "статья 12" in query:
        return "Продление вождения возможно на 2 часа, если нет подходящей парковки, пробки или погода. Нужно компенсировать отдых."

    elif "паром" in query or "поезд" in query:
        return "Если отдых прерывается из-за парома или поезда, общая продолжительность отдыха должна быть увеличена на 2 часа."

    elif "какой график" in query or "когда приеду" in query:
        return "Давайте рассчитаем маршрут. Сколько км до выгрузки?"

    else:
        return "Не нашёл в бумагах — не буду врать."

# Функция расчёта маршрута
def calculate_route(query):
    try:
        distance = int(query.split("км")[0].split(" ") [-1])
        speed = int(query.split("скорость")[1].split(" ")[1])
        is_team = "одиночка" not in query and "один" not in query
        avoid_night_driving = "ночью" in query or "избегать ночного" in query
        start_time = query.split("старт")[1].strip().split()[0] if "старт" in query else "07:00"
        date = query.split(",")[0].strip() if "," in query else "03.06.2025"

        hour_drive = 4
        rest_hours = 11
        max_daily_driving = 9
        max_weekly_driving = 56

        drive_per_hour = speed * hour_drive
        total_hours = distance / speed
        full_days = int(total_hours // 8)
        remaining_distance = distance - (full_days * 600)

        result = f"📦 ЗАДАЧА:\n📏 Расстояние: {distance} км\n🚛 Скорость: {speed} км/ч\n👤 Экипаж: {'парный' if is_team else 'одиночка'}\n🕒 Старт: {date}, {start_time}\n🧘 Режим: комфорт\n🌙 Избегать ночного вождения: {'да' if avoid_night_driving else 'нет'}\n\n---\n"

        for i in range(full_days):
            result += f"🕗 Начало смены: {start_time}\n🚛 Вождение {hour_drive} ч ≈ {drive_per_hour} км → До {add_time(start_time, hour_drive)}\n🍽️ Пауза + еда: 1 ч → До {add_time(start_time, hour_drive + 1)}\n🛌 Отдых (11 ч): До {add_time(start_time, hour_drive + rest_hours)}\n\n"

        if remaining_distance > 0:
            result += f"🕗 Начало следующей смены: {add_time(start_time, hour_drive + rest_hours)}\n🚛 Остаток пути: {remaining_distance} км ≈ {round(remaining_distance / speed, 1)} ч → До {add_time(add_time(start_time, hour_drive + rest_hours), round(remaining_distance / speed, 1))}\n🏁 Прибытие: ~{add_time(add_time(start_time, hour_drive + rest_hours), round(remaining_distance / speed, 1))} следующего дня\n📏 Общий путь: {distance} км"

        return result
    except Exception as e:
        return "⚠️ Не могу выполнить расчёт. Уточни данные."

# Простая функция для сложения времени
def add_time(current_time, hours):
    from datetime import datetime, timedelta
    time_obj = datetime.strptime(current_time, "%H:%M")
    new_time = time_obj + timedelta(hours=hours)
    return new_time.strftime("%H:%M")

@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json()
    user_query = data.get("query", "")

    if not user_query:
        return jsonify({"error": "Нет сообщения"}), 400

    try:
        max_response = process_query(user_query)
        return jsonify({"response": max_response})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
