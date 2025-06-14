import logging
import os
import openai
import tempfile
import requests
import urllib.parse
from geopy.distance import geodesic
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from dotenv import load_dotenv

# --- Настройка логирования ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Глобальные переменные и загрузка окружения ---
context_history = []
MAX_TURNS = 6
MAX_DISTANCE_KM = 50  # Максимальное расстояние для результатов (в км)

# Загрузка .env
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")
openai.api_key = OPENAI_API_KEY

# Загрузка промта системы для GPT
try:
    with open("prompt.txt", "r", encoding="utf-8") as f:
        SYSTEM_PROMPT = f.read()
except FileNotFoundError:
    SYSTEM_PROMPT = "Ты — Макс. Диспетчер, помощник и навигатор по жизни в рейсе."
    logger.warning("Файл prompt.txt не найден. Используется системный промт по умолчанию.")

# --- Функции для работы с базой знаний ---
def load_relevant_knowledge(user_input: str) -> str:
    """
    Загружает релевантную информацию из файлов базы знаний
    на основе ключевых слов в вводе пользователя.
    """
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
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        texts.append(f"📘 {filename}:\n{content}\n")
            except Exception as e:
                logger.error(f"Ошибка чтения файла базы знаний {filename}: {e}")
        else:
            logger.warning(f"Файл базы знаний не найден: {path}")

    return "\n".join(texts) or ""

# --- Функции для взаимодействия с GPT ---
async def ask_gpt(messages: list) -> dict:
    """
    Отправляет запрос к GPT-модели, пытаясь сначала GPT-4.5, затем GPT-3.5.
    """
    try:
        response = await openai.ChatCompletion.acreate(model="gpt-4.5-preview", messages=messages)
        return response
    except openai.error.OpenAIError as e:
        logger.warning(f"GPT-4.5-preview недоступен, fallback к GPT-3.5: {e}")
        try:
            response = await openai.ChatCompletion.acreate(model="gpt-3.5-turbo-1106", messages=messages)
            return response
        except openai.error.OpenAIError as e2:
            logger.error(f"GPT-3.5 тоже не сработал: {e2}")
            return None
    except Exception as e:
        logger.error(f"Неизвестная ошибка при запросе к OpenAI API: {e}")
        return None

# --- Обработчики команд и сообщений Telegram ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает команду /start."""
    await update.message.reply_text("Здорова, я — Макс. Диспетчер, друг и напарник. Пиши, говори или отправляй координаты — разберёмся!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает текстовые сообщения пользователя."""
    user_input = update.message.text.strip()
    if not user_input:
        await update.message.reply_text("Чем могу помочь?")
        return

    lowered = user_input.lower()

    if any(keyword in lowered for keyword in ["нарисуй", "покажи", "сгенерируй", "изображение", "картинку", "картина"]):
        try:
            image_response = await openai.Image.acreate(prompt=user_input, n=1, size="512x512")
            image_url = image_response['data'][0]['url']
            await update.message.reply_photo(photo=image_url, caption="🖼️ Вот как это может выглядеть:")
            return
        except openai.error.OpenAIError as e:
            logger.error(f"Ошибка генерации изображения через OpenAI API: {e}")
            await update.message.reply_text("❌ Не удалось сгенерировать изображение. Возможно, проблема с API или запросом. Попробуй позже.")
            return
        except Exception as e:
            logger.error(f"Неизвестная ошибка при генерации изображения: {e}")
            await update.message.reply_text("❌ Не удалось сгенерировать изображение. Попробуй позже.")
            return

    context_history.append({"role": "user", "content": user_input})
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    kb_snippet = load_relevant_knowledge(user_input)
    if kb_snippet:
        messages.append({"role": "system", "content": "📚 База знаний:\n" + kb_snippet})
    
    messages.extend(context_history[-MAX_TURNS:])

    response = await ask_gpt(messages)
    if response and response.choices:
        assistant_reply = response.choices[0].message.content.strip()
        context_history.append({"role": "assistant", "content": assistant_reply})
        await update.message.reply_text(assistant_reply)
    else:
        await update.message.reply_text("❌ Ошибка при запросе к GPT. Попробуй позже.")

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает голосовые сообщения пользователя."""
    try:
        file = await update.message.voice.get_file()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".oga") as f:
            await file.download_to_drive(f.name)
            audio_path = f.name

        with open(audio_path, "rb") as audio_file:
            transcript = await openai.Audio.atranscribe("whisper-1", audio_file)
            user_text = transcript.get("text", "")
        
        os.remove(audio_path)

        if not user_text:
            await update.message.reply_text("🎧 Не смог разобрать голос. Попробуй снова.")
            return

        await update.message.reply_text(f"Ты сказал: \"{user_text}\"")

        context_history.append({"role": "user", "content": user_text})
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        kb_snippet = load_relevant_knowledge(user_text)
        if kb_snippet:
            messages.append({"role": "system", "content": "📚 База знаний:\n" + kb_snippet})
        messages.extend(context_history[-MAX_TURNS:])

        response = await ask_gpt(messages)
        if response and response.choices:
            assistant_reply = response.choices[0].message.content.strip()
            context_history.append({"role": "assistant", "content": assistant_reply})
            await update.message.reply_text(assistant_reply)
        else:
            await update.message.reply_text("❌ Ошибка при запросе к GPT. Попробуй позже.")

    except openai.error.OpenAIError as e:
        logger.error(f"Ошибка при транскрибации голоса через OpenAI API: {e}")
        await update.message.reply_text("❌ Не удалось расшифровать голосовое сообщение. Возможно, проблема с API.")
    except Exception as e:
        logger.error(f"Неизвестная ошибка при обработке голосового сообщения: {e}", exc_info=True)
        await update.message.reply_text("⚠️ Не смог обработать голос. Возможно, проблема с форматом или внутренняя ошибка.")
    finally:
        if 'audio_path' in locals() and os.path.exists(audio_path):
            os.remove(audio_path)

async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает полученные координаты и предлагает выбор источника поиска."""
    try:
        lat = update.message.location.latitude
        lon = update.message.location.longitude
        context.user_data['last_location'] = (lat, lon)  # Сохраняем координаты
        await update.message.reply_text(
            "📍 Получил координаты. Выбери источник поиска:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("Google Maps", callback_data=f"search_google|{lat}|{lon}")],
                [InlineKeyboardButton("OpenStreetMap (Overpass)", callback_data=f"search_overpass|{lat}|{lon}")]
            ])
        )
    except Exception as e:
        logger.error(f"Ошибка при обработке геолокации: {e}", exc_info=True)
        await update.message.reply_text("❌ Ошибка при обработке координат. Попробуй позже.")

async def handle_callback_query(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает выбор источника поиска."""
    query = update.callback_query
    await query.answer()
    action, lat, lon = query.data.split("|")
    lat, lon = float(lat), float(lon)

    if action == "search_google":
        await search_with_google(update, context, lat, lon)
    elif action == "search_overpass":
        await search_with_overpass(update, context, lat, lon)

async def search_with_google(update: Update, context: ContextTypes.DEFAULT_TYPE, lat: float, lon: float):
    """Поиск мест через Google Places API с фильтрацией по расстоянию."""
    try:
        place_queries = [
            {"label": "🌳 Прогулка/Дост.", "type": "tourist_attraction", "keyword": "парк|достопримечательность|отдых", "radius": 5000},
            {"label": "🌳 Прогулка/Дост.", "type": "park", "keyword": "", "radius": 5000},
            {"label": "🚛 Парковка для фур", "type": "parking", "keyword": "грузовая парковка|truck parking", "radius": 10000},
            {"label": "🏨 Отель/Мотель", "type": "lodging", "keyword": "мотель|гостиница|hotel|motel", "radius": 10000},
            {"label": "🛒 Магазин (продукты)", "type": "supermarket", "keyword": "", "radius": 5000},
            {"label": "🛒 Магазин (продукты)", "type": "convenience_store", "keyword": "", "radius": 5000},
            {"label": "🧺 Прачечная", "type": "laundry", "keyword": "прачечная|самообслуживание|laundromat", "radius": 5000},
            {"label": "🧺 Прачечная", "type": None, "keyword": "прачечная самообслуживания|self-service laundry", "radius": 5000},
            {"label": "🚿 Душевые", "type": "gas_station", "keyword": "truck stop|душевые|душ для дальнобойщиков", "radius": 10000},
            {"label": "🚿 Душевые", "type": None, "keyword": "душ|сауна|truck stop showers", "radius": 10000},
        ]

        found_results_grouped = {}
        base_url = "https://maps.googleapis.com/maps/api/place/"
        user_location = (lat, lon)

        for query_info in place_queries:
            label = query_info["label"]
            place_type = query_info.get("type")
            keyword = query_info.get("keyword")
            radius = query_info.get("radius", 5000)

            url = ""
            if place_type and not keyword:
                url = (
                    f"{base_url}nearbysearch/json"
                    f"?location={lat},{lon}&type={place_type}&key={GOOGLE_MAPS_API_KEY}&language=ru&rankby=distance"
                )
            elif keyword:
                query_str = urllib.parse.quote(f"{keyword} рядом с {lat},{lon}")
                url = (
                    f"{base_url}textsearch/json"
                    f"?query={query_str}&radius={radius}&key={GOOGLE_MAPS_API_KEY}&language=ru"
                )
            else:
                logger.warning(f"Пропущен запрос: Недостаточно данных для {label}")
                continue

            try:
                logger.info(f"Google API запрос для {label}: {url}")
                res = requests.get(url)
                res.raise_for_status()
                data = res.json()

                if data.get("results"):
                    if label not in found_results_grouped:
                        found_results_grouped[label] = []
                    for place in data["results"][:3]:
                        name = place.get("name")
                        address = place.get("vicinity", "Без адреса")
                        loc = place["geometry"]["location"]
                        place_location = (loc["lat"], loc["lng"])
                        distance_km = geodesic(user_location, place_location).kilometers

                        if distance_km <= MAX_DISTANCE_KM:
                            place_id = place["place_id"]
                            maps_url = f"https://www.google.com/maps/dir/?api=1&origin={lat},{lon}&destination={loc['lat']},{loc['lng']}&travelmode=driving"
                            if (name, address) not in [(item[0], item[1]) for item in found_results_grouped[label]]:
                                found_results_grouped[label].append((name, address, maps_url, distance_km))
            except requests.exceptions.RequestException as e:
                logger.error(f"Ошибка HTTP запроса Google API для {label}: {e}")
            except Exception as e:
                logger.error(f"Ошибка обработки данных Google API для {label}: {e}")

        if found_results_grouped:
            reply = "📌 Нашёл такие места рядом (Google Maps):\n\n"
            buttons = []
            for label, places in found_results_grouped.items():
                reply += f"**{label}**:\n"
                places.sort(key=lambda x: x[3])  # Сортировка по расстоянию
                for name, address, url, distance_km in places:
                    reply += f"  • **{name}** ({distance_km:.1f} км)\n    📍 {address}\n    🔗 [Маршрут]({url})\n"
                    buttons.append([InlineKeyboardButton(text=f"{label}: {name} ({distance_km:.1f} км)", url=url)])
                reply += "\n"
            await update.callback_query.message.reply_markdown(reply, reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await update.callback_query.message.reply_text("😔 Ничего не нашёл поблизости (Google Maps).")
    except Exception as e:
        logger.error(f"Ошибка поиска Google API: {e}", exc_info=True)
        await update.callback_query.message.reply_text("❌ Ошибка при поиске через Google Maps.")

async def search_with_overpass(update: Update, context: ContextTypes.DEFAULT_TYPE, lat: float, lon: float):
    """Поиск мест через Overpass API (OpenStreetMap) с маршрутами в Google Maps."""
    try:
        place_queries = [
            {"label": "🌳 Прогулка/Дост.", "query": f'node["tourism"="attraction"](around:5000,{lat},{lon});node["leisure"="park"](around:5000,{lat},{lon});'},
            {"label": "🚛 Парковка для фур", "query": f'node["highway"="services"]["access"="truck"](around:10000,{lat},{lon});'},
            {"label": "🏨 Отель/Мотель", "query": f'node["tourism"~"hotel|motel"](around:10000,{lat},{lon});'},
            {"label": "🛒 Магазин (продукты)", "query": f'node["shop"="supermarket"](around:5000,{lat},{lon});'},
            {"label": "🧺 Прачечная", "query": f'node["shop"="laundry"](around:5000,{lat},{lon});'},
            {"label": "🚿 Душевые", "query": f'node["amenity"="shower"](around:10000,{lat},{lon});'},
        ]

        found_results_grouped = {}
        overpass_url = "http://overpass-api.de/api/interpreter"
        user_location = (lat, lon)

        for query_info in place_queries:
            label = query_info["label"]
            overpass_query = f"[out:json];{query_info['query']}out body;"

            try:
                logger.info(f"Overpass API запрос для {label}: {overpass_query}")
                res = requests.post(overpass_url, data={"data": overpass_query})
                res.raise_for_status()
                data = res.json()

                if data.get("elements"):
                    if label not in found_results_grouped:
                        found_results_grouped[label] = []
                    for element in data["elements"][:3]:
                        name = element["tags"].get("name", "Без названия")
                        # Собираем адрес из доступных тегов
                        address_parts = []
                        for tag in ["addr:street", "addr:housenumber", "addr:city", "addr:country"]:
                            if tag in element["tags"]:
                                address_parts.append(element["tags"][tag])
                        address = ", ".join(address_parts) if address_parts else "Без адреса"
                        el_lat, el_lon = element["lat"], element["lon"]
                        place_location = (el_lat, el_lon)
                        distance_km = geodesic(user_location, place_location).kilometers

                        if distance_km <= MAX_DISTANCE_KM:
                            # Формируем ссылку на Google Maps с маршрутом
                            maps_url = f"https://www.google.com/maps/dir/?api=1&origin={lat},{lon}&destination={el_lat},{el_lon}&travelmode=driving"
                            if (name, address) not in [(item[0], item[1]) for item in found_results_grouped[label]]:
                                found_results_grouped[label].append((name, address, maps_url, distance_km))
            except requests.exceptions.RequestException as e:
                logger.error(f"Ошибка HTTP запроса Overpass API для {label}: {e}")
            except Exception as e:
                logger.error(f"Ошибка обработки данных Overpass API для {label}: {e}")

        if found_results_grouped:
            reply = "📌 Нашёл такие места рядом (OpenStreetMap):\n\n"
            buttons = []
            for label, places in found_results_grouped.items():
                reply += f"**{label}**:\n"
                places.sort(key=lambda x: x[3])  # Сортировка по расстоянию
                for name, address, url, distance_km in places:
                    reply += f"  • **{name}** ({distance_km:.1f} км)\n    📍 {address}\n    🔗 [Маршрут]({url})\n"
                    buttons.append([InlineKeyboardButton(text=f"{label}: {name} ({distance_km:.1f} км)", url=url)])
                reply += "\n"
            await update.callback_query.message.reply_markdown(reply, reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await update.callback_query.message.reply_text("😔 Ничего не нашёл поблизости (OpenStreetMap). Попробуй Google Maps или уточни запрос.")
    except Exception as e:
        logger.error(f"Ошибка поиска Overpass API: {e}", exc_info=True)
        await update.callback_query.message.reply_text("❌ Ошибка при поиске через OpenStreetMap.")

# --- Запуск бота ---
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Добавляем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    app.add_handler(CallbackQueryHandler(handle_callback_query))
    
    logger.info("Бот запущен. Ожидание сообщений...")
    app.run_polling()
