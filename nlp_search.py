import spacy
import os

# Загрузка русской NLP-модели
try:
    nlp = spacy.load("ru_core_news_sm")
except OSError:
    raise SystemExit(
        "❌ Модель ru_core_news_sm не найдена. Установите её с помощью:\n"
        "python -m spacy download ru_core_news_sm"
    )

# Базовые ключевые слова для каждой категории
keywords_map = {
    "отдых": "Rezim_RTO.md",
    "смена": "Rezim_RTO.md",
    "пауза": "Rezim_RTO.md",
    "разрыв паузы": "Rezim_RTO.md",
    "тахограф": "4_tahograf_i_karty.md",
    "карта": "4_tahograf_i_karty.md",
    "поезд": "ferry_routes.md",
    "паром": "ferry_routes.md",
    "цмр": "CMR.md",
    "документ": "CMR.md",
    "комфорт": "11_komfort_i_byt.md",
    "питание": "12_pitanie_i_energiya.md"
}

# Порог сходства слов (0.5–1.0)
SIMILARITY_THRESHOLD = 0.65


def load_relevant_knowledge(user_input: str) -> str:
    """
    Находит подходящие файлы знаний на основе NLP-сравнения.
    """
    lowered = user_input.lower()
    doc = nlp(lowered)

    selected_files = set()

    for keyword, filename in keywords_map.items():
        keyword_doc = nlp(keyword)
        # Сравнение с каждым токеном в запросе
        for token in doc:
            similarity = token.similarity(keyword_doc)
            if similarity > SIMILARITY_THRESHOLD:
                print(f"[NLP] Совпадение: '{token.text}' ~ '{keyword}' ({similarity:.2f})")
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
                        print(f"[База знаний] Файл пуст: {filename}")
            except Exception as e:
                print(f"[База знаний] Ошибка чтения файла {filename}: {e}")
        else:
            print(f"[База знаний] Файл не найден: {path}")

    return "\n".join(texts) or ""
