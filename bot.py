import logging
import os
import openai
import tempfile
import requests
import urllib.parse
import asyncio
from geopy.distance import geodesic
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from dotenv import load_dotenv

# --- Настройка логирования ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG  # Установлено на DEBUG для детального анализа
)
logger = logging.getLogger(__name__)

# --- Глобальные переменные и загрузка окружения ---
MAX_TURNS_FOR_SUMMARY = 10  # Сколько последних сообщений использовать для создания сводки
MAX_DISTANCE_KM = 50        # Максимальное расстояние для результатов (в км)
REQUEST_TIMEOUT = 30        # Таймаут для внешних HTTP запросов в секундах (унифицирован)

# Загрузка .env
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY")

# --- Инициализация клиентов ---
client = openai.AsyncOpenAI(api_key=OPENAI_API_KEY)

# Загрузка промта системы для GPT из файла
try:
    with open("prompt.txt", "r", encoding="utf-8") as f:
        SYSTEM_PROMPT = f.read()
except FileNotFoundError:
    SYSTEM_PROMPT = "Ты — Макс. Диспетчер, помощник и навигатор по жизни в рейсе."
    logger.warning("Файл prompt.txt не найден. Используется системный промт по умолчанию.")

# Загрузка промта системы для GPT из файла
try:
    with open("prompt.txt", "r", encoding="utf-8") as f:
        SYSTEM_PROMPT = f.read()
except FileNotFoundError:
    SYSTEM_PROMPT = "Ты — Макс. Диспетчер, помощник и навигатор по жизни в рейсе."

# Загрузка базы знаний по ключевым словам
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
                    texts.append(f"📘 {filename}:{content}\n")

    return "\n".join(texts) or ""

# --- Форматирование ответа ---
def format_places_reply(places_grouped: dict, source_name: str, ratings=None) -> tuple[list[str], list[list[list[InlineKeyboardButton]]]]:
    """Форматирует ответ с найденными местами в виде кликабельных кнопок с иконками и рейтингами (если доступны)."""
    if not places_grouped:
        logger.debug(f"Places grouped is empty for {source_name}")
        return [f"😔 Ничего не нашёл поблизости ({source_name})."], []

    messages = []
    button_groups = []
    buttons_per_message = 5  # Ограничение на 5 кнопок на сообщение
    current_message = f"📍 Места рядом ({source_name}):"

    # Иконки для категорий
    category_icons = {
        "🌳 Парки": "🌳",
        "🏛 Достопримечательности": "🏛",
        "🚛 Парковка для фур": "🚛",
        "🏨 Отель/Мотель": "🏨",
        "🛒 Магазин": "🛒",
        "🧺 Прачечная": "🧺",
        "🚿 Душевые": "🚿"
    }

    all_buttons = []
    for label, places in places_grouped.items():
        places.sort(key=lambda x: x[3])  # Сортировка по расстоянию
        places = places[:5]  # Ограничиваем до 5 мест на категорию
        category = label.split()[1] if len(label.split()) > 1 else label  # Извлекаем категорию
        icon = category_icons.get(label, "📍")  # Иконка по умолчанию
        if ratings:
            for name, address, url, distance_km, rating in places:
                button_text = f"{icon} {category} {name} ({distance_km:.1f} км)"
                if rating and 0 <= rating <= 5:  # Проверяем, что рейтинг валиден
                    button_text += f" ★{rating:.1f}"
                all_buttons.append([InlineKeyboardButton(text=button_text, url=url)])
        else:
            for name, address, url, distance_km in places:
                button_text = f"{icon} {category} {name} ({distance_km:.1f} км)"
                all_buttons.append([InlineKeyboardButton(text=button_text, url=url)])

    logger.debug(f"Total buttons created: {len(all_buttons)} for {source_name}")

    if not all_buttons:
        return [f"😔 Ничего не нашёл поблизости ({source_name})."], []

    # Разбиваем кнопки на группы по 5
    for i in range(0, len(all_buttons), buttons_per_message):
        button_group = all_buttons[i:i + buttons_per_message]
        button_groups.append(button_group)
        messages.append(current_message)

    logger.debug(f"Messages: {len(messages)}, Button groups: {len(button_groups)} for {source_name}")
    return messages, button_groups
# --- Функции для взаимодействия с GPT ---
async def summarize_history(history: list) -> str:
    """
    [TOKEN OPTIMIZATION] Создает краткую сводку диалога, чтобы не отправлять всю историю.
    Использует более дешевую и быструю модель.
    """
    if not history:
        return ""
    
    dialogue = "\n".join([f"{msg['role']}: {msg['content']}" for msg in history])
    prompt = (
        "Создай очень краткую и сжатую сводку следующего диалога. "
        "Сохрани ключевые факты и детали, но убери все лишнее. "
        "Сводка должна помочь ассистенту понять контекст для ответа на следующий вопрос.\n\n"
        f"Диалог для анализа:\n{dialogue}"
    )
    try:
        response = await client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=250
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Ошибка при создании сводки диалога: {e}")
        return ""

async def ask_gpt(messages: list) -> str:
    """
    Отправляет запрос к GPT, используя gpt-3.5-turbo.
    """
    try:
        response = await client.chat.completions.create(model="gpt-3.5-turbo", messages=messages)
        return response.choices[0].message.content.strip()
    except openai.APIError as e:
        logger.error(f"Ошибка OpenAI API (gpt-3.5-turbo): {e}")
        return None
    except Exception as e:
        logger.error(f"Неизвестная ошибка при запросе к OpenAI API: {e}")
        return None

# --- Основная логика обработки запросов ---
async def process_user_request(update: Update, context: ContextTypes.DEFAULT_TYPE, user_input: str):
    """
    Общая функция для обработки текстовых и голосовых запросов.
    """
    if 'history' not in context.user_data:
        context.user_data['history'] = []

    context.user_data['history'].append({"role": "user", "content": user_input})
    
    history_summary = await summarize_history(context.user_data['history'][:-1])

    full_system_prompt = SYSTEM_PROMPT
    kb_snippet = load_relevant_knowledge(user_input)
    if kb_snippet:
        full_system_prompt += "\n\n📚 Используй эту информацию из базы знаний для ответа:\n" + kb_snippet

    messages = [{"role": "system", "content": full_system_prompt}]
    if history_summary:
        messages.append({"role": "system", "content": f"Вот краткая сводка предыдущего диалога для контекста:\n{history_summary}"})
    
    messages.append({"role": "user", "content": user_input})

    assistant_reply = await ask_gpt(messages)

    if assistant_reply:
        context.user_data['history'].append({"role": "assistant", "content": assistant_reply})
        context.user_data['history'] = context.user_data['history'][-MAX_TURNS_FOR_SUMMARY:]
        await update.message.reply_text(assistant_reply)
    else:
        await update.message.reply_text("❌ Ошибка при запросе к GPT. Попробуй позже.")

# --- Обработчики команд и сообщений Telegram ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает команду /start."""
    context.user_data.clear()
    await update.message.reply_text("Здорова, я — Макс. Диспетчер, друг и напарник. Пиши, говори или отправляй координаты — разберёмся!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает текстовые сообщения пользователя.
    """
    user_input = update.message.text.strip()
    if not user_input:
        return

    await process_user_request(update, context, user_input)

async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обрабатывает голосовые сообщения пользователя."""
    audio_path = None
    try:
        file = await update.message.voice.get_file()
        with tempfile.NamedTemporaryFile(delete=False, suffix=".oga") as f:
            await file.download_to_drive(f.name)
            audio_path = f.name

        with open(audio_path, "rb") as audio_file:
            transcript = await client.audio.transcriptions.create(model="whisper-1", file=audio_file)
            user_text = transcript.text.strip()
        
        if not user_text:
            await update.message.reply_text("🎧 Не смог разобрать голос. Попробуй снова.")
            return

        await update.message.reply_text(f"Ты сказал: \"{user_text}\"")
        await process_user_request(update, context, user_text)

    except openai.APIError as e:
        logger.error(f"Ошибка транскрибации голоса: {e}")
        await update.message.reply_text("❌ Не удалось расшифровать голосовое сообщение.")
    except Exception as e:
        logger.error(f"Неизвестная ошибка при обработке голоса: {e}", exc_info=True)
        await update.message.reply_text("⚠️ Не смог обработать голос. Внутренняя ошибка.")
    finally:
        if audio_path and os.path.exists(audio_path):
            os.remove(audio_path)

# --- Обработчики геолокации ---
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
        logger.error(f"Ошибка при обработке геолокации: {e}", exc_info=True)
        await update.message.reply_text("❌ Ошибка при обработке координат.")

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
        logger.error(f"Ошибка разбора callback_data: {query.data}, {e}")
        await query.edit_message_text(text="Произошла ошибка, попробуйте снова.")

# --- Поиск через Google API ---
async def search_with_google(query, context: ContextTypes.DEFAULT_TYPE, lat: float, lon: float):
    """Поиск мест через Google Places API с фильтрацией по расстоянию и пагинацией."""
    try:
        place_queries = [
            {"label": "🌳 Парки", "type": "park", "keyword": "park", "radius": 20000},
            {"label": "🏛 Достопримечательности", "type": "tourist_attraction", "keyword": "tourist attraction|museum|landmark", "radius": 20000},
            {"label": "🚛 Парковка для фур", "keyword": "грузовая парковка|truck parking", "radius": 10000},
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
                query_str = urllib.parse.quote(keyword)
                urls.append(
                    f"{base_url}textsearch/json"
                    f"?query={query_str}&location={lat},{lon}&radius={radius}&key={GOOGLE_MAPS_API_KEY}&language=ru"
                )

            for url in urls:
                while True:
                    try:
                        request_url = f"{url}&pagetoken={next_page_token}" if next_page_token else url
                        logger.info(f"Google API запрос для {label}: {request_url}")
                        res = requests.get(request_url, timeout=REQUEST_TIMEOUT)
                        res.raise_for_status()
                        data = res.json()
                        logger.info(f"Статус Google API для {label}: {data.get('status')}")
                        logger.debug(f"Сырой ответ Google API для {label}: {data}")

                        if data.get("status") in ["OVER_QUERY_LIMIT", "ZERO_RESULTS", "REQUEST_DENIED"]:
                            logger.warning(f"Google API вернул статус {data.get('status')} для {label}: {data.get('error_message', '')}")
                            break

                        if data.get("results"):
                            if label not in found_results_grouped:
                                found_results_grouped[label] = []
                            for place in data["results"][:15]:
                                name = place.get("name", "Без названия")
                                address = place.get("vicinity", "Без адреса")
                                loc = place["geometry"]["location"]
                                place_location = (loc["lat"], loc["lng"])
                                distance_km = geodesic(user_location, place_location).kilometers
                                rating = place.get("rating")  # Может быть None

                                if distance_km <= MAX_DISTANCE_KM:
                                    maps_url = f"https://www.google.com/maps/dir/?api=1&origin={lat},{lon}&destination={loc['lat']},{loc['lng']}&travelmode=driving"
                                    unique_key = (name, address)
                                    if unique_key not in [(item[0], item[1]) for item in found_results_grouped[label]]:
                                        found_results_grouped[label].append((name, address, maps_url, distance_km, rating if rating else None))

                        next_page_token = data.get("next_page_token")
                        if not next_page_token:
                            break
                        await asyncio.sleep(2)

                    except requests.exceptions.RequestException as e:
                        logger.error(f"Ошибка HTTP запроса Google API для {label}: {e}")
                        break
                    except Exception as e:
                        logger.error(f"Ошибка обработки данных Google API для {label}: {e}")
                        break

        messages, button_groups = format_places_reply(found_results_grouped, "Google Maps")
        if not button_groups:
            await query.message.reply_markdown(messages[0])
        else:
            for msg, buttons in zip(messages, button_groups):
                await query.message.reply_markdown(msg, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        logger.error(f"Ошибка поиска Google API: {e}", exc_info=True)
        await query.message.reply_text("❌ Ошибка при поиске через Google Maps. Возможно, превышен лимит запросов или проблема с подключением.")

# --- Поиск через Overpass API ---
async def search_with_overpass(query, context: ContextTypes.DEFAULT_TYPE, lat: float, lon: float):
    """Поиск мест через Overpass API (OpenStreetMap)."""
    try:
        place_queries = [
            {"label": "🌳 Парки", "query": f'node["leisure"="park"](around:20000,{lat},{lon});'},
            {"label": "🏛 Достопримечательности", "query": f'node["tourism"~"attraction|museum|monument"](around:20000,{lat},{lon});'},
            {"label": "🚛 Парковка для фур", "query": f'node["highway"="services"]["access"="truck"](around:20000,{lat},{lon});'},
            {"label": "🏨 Отель/Мотель", "query": f'node["tourism"~"hotel|motel"](around:20000,{lat},{lon});'},
            {"label": "🛒 Магазин", "query": f'node["shop"="supermarket"](around:10000,{lat},{lon});'},
            {"label": "🧺 Прачечная", "query": f'node["shop"="laundry"](around:10000,{lat},{lon});'},
            {"label": "🚿 Душевые", "query": f'node["amenity"="shower"](around:20000,{lat},{lon});'},
        ]
        found_results_grouped = {}
        overpass_url = "http://overpass-api.de/api/interpreter"
        user_location = (lat, lon)

        for query_info in place_queries:
            label = query_info["label"]
            overpass_query = f"[out:json];{query_info['query']}out body;"

            try:
                logger.info(f"Overpass API запрос для {label}: {overpass_query}")
                res = requests.post(overpass_url, data={"data": overpass_query}, timeout=REQUEST_TIMEOUT)
                res.raise_for_status()
                data = res.json()
                logger.debug(f"Результаты Overpass API для {label}: {data.get('elements', [])}")

                if data.get("elements"):
                    if label not in found_results_grouped:
                        found_results_grouped[label] = []
                    for element in data["elements"][:5]:  # Ограничиваем до 5 мест
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
                                logger.debug(f"Добавлено место: {name}, {distance_km:.2f} км для {label}")
                                found_results_grouped[label].append((name, address, maps_url, distance_km))
                await asyncio.sleep(1)  # Задержка между запросами
            except requests.exceptions.RequestException as e:
                logger.error(f"Ошибка HTTP запроса Overpass API для {label}: {e}")
            except Exception as e:
                logger.error(f"Ошибка обработки данных Overpass API для {label}: {e}")

        messages, button_groups = format_places_reply(found_results_grouped, "OpenStreetMap")
        if not button_groups:
            await query.message.reply_markdown(messages[0])
        else:
            for msg, buttons in zip(messages, button_groups):
                await query.message.reply_markdown(msg, reply_markup=InlineKeyboardMarkup(buttons))
    except Exception as e:
        logger.error(f"Ошибка поиска Overpass API: {e}", exc_info=True)
        await query.message.reply_text("❌ Ошибка при поиске через OpenStreetMap.")

# --- Запуск бота ---
if __name__ == '__main__':
    try:
        if not all([TELEGRAM_TOKEN, OPENAI_API_KEY, GOOGLE_MAPS_API_KEY]):
            logger.critical("Не определены все необходимые переменные окружения!")
            raise ValueError("Missing environment variables")
        
        app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
        
        app.add_handler(CommandHandler("start", start))
        app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
        app.add_handler(MessageHandler(filters.VOICE, handle_voice))
        app.add_handler(MessageHandler(filters.LOCATION, handle_location))
        app.add_handler(CallbackQueryHandler(handle_callback_query))
        
        logger.info("Бот успешно запущен. Ожидание сообщений...")
        app.run_polling()
    except Exception as e:
        logger.critical(f"Критическая ошибка при запуске бота: {e}", exc_info=True)
        raise
