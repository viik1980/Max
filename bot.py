import logging
import os
import openai
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from dotenv import load_dotenv
import requests
import asyncio
from urllib.parse import quote as urllib_quote
from geopy.distance import geodesic
from openai import AsyncOpenAI
import tempfile

# --- Настройки ---
user_contexts = {}  # {user_id: [{"role": "user", "content": "..."}, ...]}
MAX_TURNS = 3
MAX_DISTANCE_KM = 40  # Максимальное расстояние для результатов (в км)
REQUEST_TIMEOUT = 15  # Таймаут для внешних HTTP-запросов в секундах

# --- Загрузка .env ---
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

# Инициализация клиента OpenAI v1+
client = AsyncOpenAI(api_key=OPENAI_API_KEY)

# --- Логирование ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- Загрузка промта ---
try:
    with open("prompt.txt", "r", encoding="utf-8") as f:
        SYSTEM_PROMPT = f.read()
except FileNotFoundError:
    SYSTEM_PROMPT = "Ты — Макс. Диспетчер, помощник и навигатор по жизни в рейсе."

# --- Загрузка базы знаний по ключевым словам ---
def load_relevant_knowledge(user_input: str) -> str:
    keywords_map = {
        # Режим RTO
        "отдых": "Rezim_RTO.md",
        "смена": "Rezim_RTO.md",
        "пауза": "Rezim_RTO.md",
        "разрыв паузы": "Rezim_RTO.md",
        "режим отдыха": "Rezim_RTO.md",
        "45 часов": "Rezim_RTO.md",
        "расчитай": "Rezim_RTO.md",

        # Паромы
        "поезд": "ferry_routes.md",
        "паром": "ferry_routes.md",
        "переправа": "ferry_routes.md",

        # CMR
        "цмр": "CMR.md",
        "cmr": "CMR.md",
        "документ": "CMR.md",
        "накладная": "CMR.md",

        # Тахограф
        "тахограф": "4_tahograf_i_karty.md",
        "карта тахографа": "4_tahograf_i_karty.md",

        # Комфорт
        "комфорт": "11_komfort_i_byt.md",
        "бытовые условия": "11_komfort_i_byt.md",

        # Питание
        "питание": "12_pitanie_i_energiya.md",
        "еда": "12_pitanie_i_energiya.md"
    }

    selected_files = set()
    lowered = user_input.lower()

    for keyword, filename in keywords_map.items():
        if keyword in lowered:
            logging.info(f"[База знаний] Совпадение найдено: '{keyword}' → {filename}")
            selected_files.add(filename)

    texts = []
    for filename in sorted(selected_files):
        path = os.path.join("knowledge", filename)
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        texts.append(f"📘 {filename}:\n{content}\n")
                    else:
                        logging.warning(f"[База знаний] Файл пуст: {filename}")
            except Exception as e:
                logging.error(f"[База знаний] Ошибка чтения файла {filename}: {e}")
        else:
            logging.warning(f"[База знаний] Файл не найден: {path}")

    return "\n".join(texts) or ""

# --- GPT-запрос (асинхронный, совместимый с openai>=1.0.0) ---
async def ask_gpt(messages):
    try:
        response = await client.chat.completions.create(
            model="gpt-5",
            messages=messages,
            temperature=1,
            max_tokens=4000,
            top_p=1.0,
            frequency_penalty=0.0,
            presence_penalty=0.0
        )
        return response
    except Exception as e:
        logging.warning(f"[GPT] gpt-5 недоступна, fallback на gpt-4.1-turbo: {e}")
        try:
            response = await client.chat.completions.create(
                model="gpt-4.1",
                messages=messages,
                temperature=0.7,
                max_tokens=4000
            )
            return response
        except Exception as e2:
            logging.warning(f"[GPT] gpt-4.1-turbo недоступна, fallback на gpt-3.5-turbo: {e2}")
            try:
                response = await client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=messages,
                    temperature=0.2,
                    max_tokens=4000
                )
                return response
            except Exception as e3:
                logging.error(f"[GPT] Все модели GPT не сработали: {e3}")
                return None

# --- Команда /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Здарова, я — Макс. Диспетчер, друг и напарник. Пиши, говори или отправляй координаты — разберёмся!")

# --- Обработка текстовых сообщений ---
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_input = update.message.text.strip()
    if not user_input:
        await update.message.reply_text("Чем могу помочь?")
        return

    user_id = update.effective_user.id
    if user_id not in user_contexts:
        user_contexts[user_id] = []

    # Сохраняем пользовательский ввод
    user_contexts[user_id].append({"role": "user", "content": user_input})
    
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    kb_snippet = load_relevant_knowledge(user_input)
    
    if kb_snippet:
        # Заставляем модель использовать контекст
        messages.append({
            "role": "system",
            "content": "⚠️ ВНИМАНИЕ: ОТВЕЧАЙ ТОЛЬКО НА ОСНОВЕ СЛЕДУЮЩИХ ДАННЫХ ИЗ БАЗЫ ЗНАНИЙ:\n" + kb_snippet
        })
    
    # Добавляем историю диалога
    messages += user_contexts[user_id][-MAX_TURNS:]

    # Отправляем в GPT
    response = await ask_gpt(messages)
    
    if response and response.choices:
        assistant_reply = response.choices[0].message.content.strip()
        user_contexts[user_id].append({"role": "assistant", "content": assistant_reply})
        await update.message.reply_text(assistant_reply)
    else:
        await update.message.reply_text("❌ Ошибка при запросе к GPT. Попробуй позже.")

# --- Обработка голосовых сообщений ---
async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        file = await update.message.voice.get_file()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".oga") as f:
            await file.download_to_drive(f.name)
            audio_path = f.name

        with open(audio_path, "rb") as audio_file:
            transcript = await client.audio.transcriptions.create(model="whisper-1", file=audio_file)
            user_text = transcript.text

        os.remove(audio_path)  # Удаляем временный файл

        if not user_text:
            await update.message.reply_text("🎧 Не смог разобрать голос. Попробуй снова.")
            return

        await update.message.reply_text(f"Ты сказал: {user_text}")

        user_id = update.effective_user.id
        if user_id not in user_contexts:
            user_contexts[user_id] = []

        user_contexts[user_id].append({"role": "user", "content": user_text})
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        kb_snippet = load_relevant_knowledge(user_text)

        if kb_snippet:
            messages.append({
                "role": "system",
                "content": "⚠️ ВНИМАНИЕ: ОТВЕЧАЙ ТОЛЬКО НА ОСНОВЕ СЛЕДУЮЩИХ ДАННЫХ:\n" + kb_snippet
            })

        messages += user_contexts[user_id][-MAX_TURNS:]
        
        response = await ask_gpt(messages)
        
        if response and response.choices:
            assistant_reply = response.choices[0].message.content.strip()
            user_contexts[user_id].append({"role": "assistant", "content": assistant_reply})
            await update.message.reply_text(assistant_reply)
        else:
            await update.message.reply_text("❌ Ошибка при запросе к GPT. Попробуй позже.")
    except Exception as e:
        logging.error(f"[ERROR] Голосовая ошибка: {e}")
        await update.message.reply_text("⚠️ Не смог обработать голос. Возможно, проблема с форматом.")

# --- Обработка геолокации ---
async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает полученные координаты и предлагает выбор источника поиска."""
    try:
        lat = update.message.location.latitude
        lon = update.message.location.longitude
        context.user_data['last_location'] = (lat, lon)
        await update.message.reply_text(
            "📍 Получил координаты. Выбери источник поиска:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Google Maps", callback_data=f"search_google|{lat}|{lon}")],
                [InlineKeyboardButton("OpenStreetMap", callback_data=f"search_overpass|{lat}|{lon}")]
            ])
        )
    except Exception as e:
        logging.error(f"Ошибка при обработке геолокации: {e}", exc_info=True)
        await update.message.reply_text("❌ Ошибка при обработке координат.")

# --- Обработка кнопок обратного вызова ---
async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает выбор источника поиска."""
    query = update.callback_query
    await query.answer()
    try:
        action, lat_str, lon_str = query.data.split("|")
        lat, lon = float(lat_str), float(lon_str)
        source_name = "Google Maps" if action == 'search_google' else "OpenStreetMap"
        await query.edit_message_text(text=f"Ищу через {source_name}...")
        if action == "search_google":
            await search_with_google(query, context, lat, lon)
        elif action == "search_overpass":
            await search_with_overpass(query, context, lat, lon)
    except (ValueError, IndexError) as e:
        logging.error(f"Ошибка разбора callback_data: {query.data}, {e}")
        await query.edit_message_text(text="Произошла ошибка, попробуйте снова.")

# --- Поиск через Google API ---
async def search_with_google(query, context: ContextTypes.DEFAULT_TYPE, lat: float, lon: float):
    """Поиск мест через Google Places API с фильтрацией по расстоянию и пагинацией."""
    try:
        place_queries = [
            {"label": "🌳 Парки", "type": "park", "keyword": "park", "radius": 20000},
            {"label": "🏛 Достопримечательности", "type": "tourist_attraction", "keyword": "tourist attraction|museum|landmark", "radius": 20000},
            {"label": "🅿️ Парковка для фур", "keyword": "грузовая парковка|truck parking", "radius": 10000},
            {"label": "🏨 Отель/Мотель", "type": "lodging", "keyword": "мотель|гостиница|hotel|motel", "radius": 10000},
            {"label": "🛒 Магазин", "type": "supermarket", "radius": 5000},
            {"label": "🧺 Прачечная", "keyword": "прачечная самообслуживания|self-service laundry", "radius": 5000},
            {"label": "🚿 Душевые", "keyword": "душ|сауна|truck stop showers", "radius": 10000},
        ]
        found_results_grouped = {}
        base_url = "https://maps.googleapis.com/maps/api/place/"
        user_location = (lat, lon)

        for query_info in place_queries:
            label = query_info["label"]
            place_type = query_info.get("type")
            keyword = query_info.get("keyword")
            radius = query_info.get("radius", 10000)
            next_page_token = None
            urls = []
            if place_type:
                urls.append(
                    f"{base_url}nearbysearch/json"
                    f"?location={lat},{lon}&type={place_type}&rankby=distance&key={GOOGLE_MAPS_API_KEY}"
                )
            if keyword:
                query_str = urllib_quote(keyword)
                urls.append(
                    f"{base_url}textsearch/json"
                    f"?query={query_str}&location={lat},{lon}&radius={radius}&key={GOOGLE_MAPS_API_KEY}&language=ru"
                )

            for url in urls:
                while True:
                    try:
                        if next_page_token:
                            paginated_url = f"{url}&pagetoken={next_page_token}"
                            logging.info(f"Google API пагинация для {label}: {paginated_url}")
                            res = requests.get(paginated_url, timeout=REQUEST_TIMEOUT)
                        else:
                            logging.info(f"Google API запрос для {label}: {url}")
                            res = requests.get(url, timeout=REQUEST_TIMEOUT)
                        res.raise_for_status()
                        data = res.json()
                        logging.info(f"Статус Google API для {label}: {data.get('status')}")
                        if data.get("status") != "OK":
                            logging.warning(f"Google API вернул статус {data.get('status')} для {label}: {data.get('error_message', '')}")
                            break
                        if data.get("results"):
                            if label not in found_results_grouped:
                                found_results_grouped[label] = []
                            for place in data["results"][:15]:
                                name = place.get("name")
                                address = place.get("vicinity", "Без адреса")
                                loc = place["geometry"]["location"]
                                place_location = (loc["lat"], loc["lng"])
                                distance_km = geodesic(user_location, place_location).kilometers
                                if distance_km <= MAX_DISTANCE_KM:
                                    maps_url = f"https://www.google.com/maps/dir/?api=1&origin={lat},{lon}&destination={loc['lat']},{loc['lng']}&travelmode=driving"
                                    if (name, address) not in [(item[0], item[1]) for item in found_results_grouped[label]]:
                                        found_results_grouped[label].append((name, address, maps_url, distance_km))
                            next_page_token = data.get("next_page_token")
                            if not next_page_token:
                                break
                            await asyncio.sleep(2)
                    except requests.exceptions.RequestException as e:
                        logging.error(f"Ошибка HTTP запроса Google API для {label}: {e}")
                        break
                    except Exception as e:
                        logging.error(f"Ошибка обработки данных Google API для {label}: {e}")
                        break

        messages, buttons = format_places_reply(found_results_grouped, "Google Maps")
        for msg in messages:
            await query.message.reply_markdown(msg, reply_markup=buttons if msg == messages[-1] else None)
    except Exception as e:
        logging.error(f"Ошибка поиска Google API: {e}", exc_info=True)
        await query.message.reply_text("❌ Ошибка при поиске через Google Maps.")

# --- Поиск через Overpass API ---
async def search_with_overpass(query, context: ContextTypes.DEFAULT_TYPE, lat: float, lon: float):
    """Поиск мест через Overpass API (OpenStreetMap)."""
    try:
        place_queries = [
            {"label": "🌳 Парки", "query": f'node["leisure"="park"](around:10000,{lat},{lon});'},
            {"label": "🏛 Достопримечательности", "query": f'node["tourism"~"attraction|museum|monument"](around:10000,{lat},{lon});'},
            {"label": "🅿️ Парковка для фур", "query": f'node["highway"="services"]["access"="truck"](around:10000,{lat},{lon});'},
            {"label": "🏨 Отель/Мотель", "query": f'node["tourism"~"hotel|motel"](around:10000,{lat},{lon});'},
            {"label": "🛒 Магазин", "query": f'node["shop"="supermarket"](around:5000,{lat},{lon});'},
            {"label": "🧺 Прачечная", "query": f'node["shop"="laundry"](around:5000,{lat},{lon});'},
            {"label": "🚿 Душевые", "query": f'node["amenity"="shower"](around:10000,{lat},{lon});'},
        ]
        found_results_grouped = {}
        overpass_url = "http://overpass-api.de/api/interpreter"
        user_location = (lat, lon)
        for query_info in place_queries:
            label = query_info["label"]
            overpass_query = f"[out:json];({query_info['query']});out body;"
            try:
                logging.info(f"Overpass API запрос для {label}: {overpass_query}")
                res = requests.post(overpass_url, data={"data": overpass_query}, timeout=REQUEST_TIMEOUT)
                res.raise_for_status()
                data = res.json()
                logging.info(f"Результаты Overpass API для {label}: {len(data.get('elements', []))} элементов")
                if data.get("elements"):
                    if label not in found_results_grouped:
                        found_results_grouped[label] = []
                    for element in data["elements"][:10]:
                        name = element["tags"].get("name", "Без названия")
                        address_parts = []
                        for tag in ["addr:street", "addr:housenumber", "addr:city", "addr:country"]:
                            if tag in element["tags"]:
                                address_parts.append(element["tags"][tag])
                        address = ", ".join(address_parts) if address_parts else "Без адреса"
                        el_lat, el_lon = element["lat"], element["lon"]
                        place_location = (el_lat, el_lon)
                        distance_km = geodesic(user_location, place_location).kilometers
                        if distance_km <= MAX_DISTANCE_KM:
                            maps_url = f"https://www.google.com/maps/dir/?api=1&origin={lat},{lon}&destination={el_lat},{el_lon}&travelmode=driving"
                            if (name, address) not in [(item[0], item[1]) for item in found_results_grouped[label]]:
                                found_results_grouped[label].append((name, address, maps_url, distance_km))
            except requests.exceptions.RequestException as e:
                logging.error(f"Ошибка HTTP запроса Overpass API для {label}: {e}")
            except Exception as e:
                logging.error(f"Ошибка обработки данных Overpass API для {label}: {e}")
        messages, buttons = format_places_reply(found_results_grouped, "OpenStreetMap")
        for msg in messages:
            await query.message.reply_markdown(msg, reply_markup=buttons if msg == messages[-1] else None)
    except Exception as e:
        logging.error(f"Ошибка поиска Overpass API: {e}", exc_info=True)
        await query.message.reply_text("❌ Ошибка при поиске через OpenStreetMap.")

# Форматирование ответа с найденными местами
def format_places_reply(results, source):
    messages = []
    buttons = []

    if not results:
        return ["❌ Ничего не найдено."], None

    for label, places in results.items():
        if places:
            # Сортировка по расстоянию
            places.sort(key=lambda x: x[3])
            msg = f"*{label}* ({source}):\n"
            for name, address, url, dist_km in places[:5]:
                msg += f"- [{name}]({url}), {address} | 🚗 {dist_km:.1f} км\n"
            messages.append(msg)
    
    # Можно добавить кнопку для просмотра всех результатов, если их много
    # buttons.append([InlineKeyboardButton("Показать все", callback_data="show_all_places")])
    
    return messages, InlineKeyboardMarkup(buttons) if buttons else None

# --- Запуск бота ---
if __name__ == '__main__':
    if not all([TELEGRAM_TOKEN, OPENAI_API_KEY, GOOGLE_MAPS_API_KEY]):
        logging.critical("Не установлены все необходимые переменные окружения!")
    else:
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        app.add_handler(MessageHandler(filters.VOICE, handle_voice))
        app.add_handler(MessageHandler(filters.LOCATION, handle_location))
        app.add_handler(CallbackQueryHandler(handle_callback_query))
        logging.info("Бот запущен. Ожидание сообщений...")
        app.run_polling()
