import logging
import os
import openai
import tempfile
import requests
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv

# --- Настройка логирования ---
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- Глобальные переменные и загрузка окружения ---
# Простая память между сообщениями
context_history = []
MAX_TURNS = 6

# Загрузка .env
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
Maps_API_KEY = os.getenv("Maps_API_KEY")
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

    # Генерация изображения
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

    # Подготовка сообщений для GPT
    context_history.append({"role": "user", "content": user_input})
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    
    kb_snippet = load_relevant_knowledge(user_input)
    if kb_snippet:
        messages.append({"role": "system", "content": "📚 База знаний:\n" + kb_snippet})
    
    # Добавляем последние сообщения для поддержания контекста
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
        # Используем NamedTemporaryFile для безопасной работы с временными файлами
        with tempfile.NamedTemporaryFile(delete=False, suffix=".oga") as f:
            await file.download_to_drive(f.name)
            audio_path = f.name

        with open(audio_path, "rb") as audio_file:
            transcript = await openai.Audio.atranscribe("whisper-1", audio_file)
            user_text = transcript.get("text", "")
        
        # Удаляем временный файл
        os.remove(audio_path)

        if not user_text:
            await update.message.reply_text("🎧 Не смог разобрать голос. Попробуй снова.")
            return

        await update.message.reply_text(f"Ты сказал: \"{user_text}\"") # Добавил кавычки для наглядности

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
        # Убедимся, что временный файл удален, даже если произошла ошибка
        if 'audio_path' in locals() and os.path.exists(audio_path):
            os.remove(audio_path)


async def handle_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает полученные координаты и ищет места поблизости,
    используя оптимизированные запросы к Google Places API.
    """
    try:
        lat = update.message.location.latitude
        lon = update.message.location.longitude
        await update.message.reply_text("📍 Получил координаты. Ищу поблизости нужные места...")

        # Определяем типы мест и ключевые слова для более точного поиска
        # Используем список словарей для лучшей читаемости и расширяемости
        place_queries = [
            # Достопримечательности / Прогулки
            {"label": "🌳 Прогулка/Дост.", "type": "tourist_attraction", "keyword": "парк|достопримечательность|отдых", "radius": 15000},
            {"label": "🌳 Прогулка/Дост.", "type": "park", "keyword": "", "radius": 15000},
            
            # Парковка для грузовых
            {"label": "🚛 Парковка для фур", "type": "parking", "keyword": "грузовая парковка|truck parking|парковка для фур", "radius": 50000},
            
            # Отель / Мотель
            {"label": "🏨 Отель/Мотель", "type": "lodging", "keyword": "мотель|гостиница|hotel|motel", "radius": 20000},
            
            # Магазины с продуктами
            {"label": "🛒 Магазин (продукты)", "type": "supermarket", "keyword": "", "radius": 10000},
            {"label": "🛒 Магазин (продукты)", "type": "convenience_store", "keyword": "", "radius": 10000},
            
            # Стиральные машинки (прачечные)
            {"label": "🧺 Прачечная", "type": "laundry", "keyword": "прачечная|самообслуживание|laundromat", "radius": 10000},
            # Если прямой тип не всегда работает, можно попробовать textsearch без типа
            {"label": "🧺 Прачечная", "type": None, "keyword": "прачечная самообслуживания|laundry service|self-service laundry", "radius": 10000},
            
            # Душевые (сложно найти напрямую, можно искать места, где они часто бывают)
            {"label": "🚿 Душевые", "type": "gas_station", "keyword": "truck stop|душевые|душ для дальнобойщиков", "radius": 50000},
            {"label": "🚿 Душевые", "type": None, "keyword": "душ|сауна|truck stop showers", "radius": 50000}
        ]

        found_results_grouped = {} # Словарь для группировки результатов по категориям
        
        for query_info in place_queries:
            label = query_info["label"]
            place_type = query_info.get("type")
            keyword = query_info.get("keyword")
            radius = query_info.get("radius", 7000) # По умолчанию 7 км, но можно переопределить

            base_url = "https://maps.googleapis.com/maps/api/place/"
            
            # Выбираем тип запроса: nearbysearch или textsearch
            url = ""
            if place_type and not keyword: # Если есть тип, но нет специфического ключевого слова
                url = (
                    f"{base_url}nearbysearch/json"
                    f"?location={lat},{lon}&radius={radius}&type={place_type}&key={Maps_API_KEY}&language=ru"
                )
            elif keyword: # Если есть ключевое слово (предпочтительнее Text Search для сложных запросов)
                # Для Text Search рекомендуется использовать query, включающий местоположение для релевантности
                query_str = f"{keyword} рядом с {lat},{lon}"
                url = (
                    f"{base_url}textsearch/json"
                    f"?query={query_str}&radius={radius}&key={Maps_API_KEY}&language=ru"
                )
            else:
                logger.warning(f"Пропущен запрос: Недостаточно данных для {label}")
                continue # Пропускаем, если нет ни типа, ни ключевого слова

            try:
                logger.info(f"Выполняю запрос для {label}: {url}")
                res = requests.get(url)
                res.raise_for_status() # Вызывает исключение для статусов 4xx/5xx
                data = res.json()

                if data.get("results"):
                    if label not in found_results_grouped:
                        found_results_grouped[label] = []

                    for place in data["results"][:3]: # Берем до 3 результатов из каждой категории
                        name = place.get("name")
                        address = place.get("vicinity", "Без адреса")
                        loc = place["geometry"]["location"]
                        place_id = place["place_id"]
                        
                        # URL для Google Maps, используем place_id для большей точности
                        maps_url = f"https://www.google.com/maps/search/?api=1&query={loc['lat']},{loc['lng']}&query_place_id={place_id}"
                        
                        # Проверяем, чтобы не дублировать результаты
                        if (name, address) not in [(item[0], item[1]) for item in found_results_grouped[label]]:
                            found_results_grouped[label].append((name, address, maps_url))
            except requests.exceptions.RequestException as e:
                logger.error(f"Ошибка HTTP запроса для {label}: {e}")
            except Exception as e:
                logger.error(f"Ошибка обработки данных для {label}: {e}")

        # Формируем ответное сообщение и кнопки
        if found_results_grouped:
            reply = "📌 Нашёл такие места рядом:\n\n"
            buttons = []
            
            for label, places in found_results_grouped.items():
                reply += f"**{label}**:\n"
                for name, address, url in places:
                    reply += f"  • **{name}**\n    📍 {address}\n    🔗 [Маршрут]({url})\n"
                    buttons.append([InlineKeyboardButton(text=f"{label}: {name}", url=url)])
                reply += "\n" # Добавляем пустую строку для разделения категорий

            await update.message.reply_markdown(reply, reply_markup=InlineKeyboardMarkup(buttons))
        else:
            await update.message.reply_text("😔 Ничего не нашёл поблизости.")
    
    except Exception as e:
        logger.error(f"Критическая ошибка при обработке геолокации: {e}", exc_info=True)
        await update.message.reply_text("❌ Ошибка при поиске. Попробуй позже.")

# --- Запуск бота ---
if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    
    # Добавляем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.VOICE, handle_voice))
    app.add_handler(MessageHandler(filters.LOCATION, handle_location))
    
    logger.info("Бот запущен. Ожидание сообщений...")
    app.run_polling()
