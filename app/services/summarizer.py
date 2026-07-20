import re
from collections import Counter

STOPWORDS = {
    "и",
    "в",
    "во",
    "на",
    "с",
    "со",
    "к",
    "ко",
    "у",
    "о",
    "об",
    "от",
    "до",
    "по",
    "за",
    "из",
    "для",
    "не",
    "но",
    "а",
    "или",
    "что",
    "это",
    "как",
    "так",
    "то",
    "же",
    "ли",
    "бы",
    "был",
    "была",
    "были",
    "быть",
    "есть",
    "ее",
    "её",
    "их",
    "его",
    "она",
    "он",
    "они",
    "мы",
    "вы",
    "я",
    "ты",
    "мне",
    "нам",
    "вас",
    "нас",
    "the",
    "a",
    "an",
    "and",
    "or",
    "but",
    "to",
    "of",
    "in",
    "on",
    "for",
    "with",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "this",
    "that",
    "it",
    "as",
    "at",
    "by",
    "from",
}

DATE_PATTERN = re.compile(
    r"\b(?:\d{1,2}[./-]\d{1,2}[./-]\d{2,4}|\d{4}-\d{2}-\d{2}|"
    r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s+\d{1,2},?\s+\d{4}|"
    r"\d{1,2}\s+(?:января|февраля|марта|апреля|мая|июня|июля|августа|"
    r"сентября|октября|ноября|декабря)\s+\d{4})\b",
    flags=re.IGNORECASE | re.UNICODE,
)

ACTION_MARKERS = (
    "must",
    "should",
    "need to",
    "needs to",
    "required",
    "deadline",
    "todo",
    "action",
    "next step",
    "нужно",
    "необходимо",
    "следует",
    "дедлайн",
    "срок",
    "задача",
    "сделать",
)

DOCUMENT_TYPE_RULES = {
    "contract": [
        "agreement",
        "contract",
        "party",
        "terms",
        "liability",
        "договор",
        "соглашение",
        "сторона",
    ],
    "invoice": [
        "invoice",
        "payment",
        "amount due",
        "subtotal",
        "счет",
        "счёт",
        "оплата",
        "сумма",
    ],
    "meeting notes": [
        "meeting",
        "agenda",
        "minutes",
        "attendees",
        "митинг",
        "встреча",
        "повестка",
    ],
    "technical doc": ["api", "endpoint", "architecture", "install", "configuration"],
    "research": ["abstract", "methodology", "findings", "study", "исследование", "методология"],
}


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def split_into_sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []

    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [s.strip() for s in sentences if s.strip()]


def tokenize_words(text: str) -> list[str]:
    words = re.findall(r"\b[\w-]+\b", text.lower(), flags=re.UNICODE)
    return [w for w in words if len(w) > 2 and w not in STOPWORDS and not w.isdigit()]


def calculate_word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text, flags=re.UNICODE))


def estimate_reading_time_minutes(word_count: int, words_per_minute: int = 200) -> int:
    if word_count <= 0:
        return 0
    return max(1, round(word_count / words_per_minute))


def score_sentences(sentences: list[str]) -> list[tuple[str, int]]:
    all_words = tokenize_words(" ".join(sentences))
    freq = Counter(all_words)

    scored = []
    for sentence in sentences:
        sentence_words = tokenize_words(sentence)
        score = sum(freq[word] for word in sentence_words)
        scored.append((sentence, score))

    return scored


def build_short_summary(text: str, max_sentences: int = 3) -> str:
    sentences = split_into_sentences(text)
    if not sentences:
        return ""

    scored = score_sentences(sentences)
    top_sentences = sorted(scored, key=lambda x: x[1], reverse=True)[:max_sentences]

    ordered = []
    top_set = {sentence for sentence, _ in top_sentences}
    for sentence in sentences:
        if sentence in top_set:
            ordered.append(sentence)

    return " ".join(ordered).strip()


def extract_key_points(text: str, max_points: int = 5) -> list[str]:
    sentences = split_into_sentences(text)
    if not sentences:
        return []

    scored = score_sentences(sentences)
    ranked = sorted(scored, key=lambda x: x[1], reverse=True)

    result = []
    for sentence, _ in ranked:
        if len(sentence.split()) >= 6:
            result.append(sentence)
        if len(result) >= max_points:
            break

    return result


def extract_keywords(text: str, max_keywords: int = 10) -> list[str]:
    words = tokenize_words(text)
    if not words:
        return []

    freq = Counter(words)
    return [word for word, _ in freq.most_common(max_keywords)]


def build_bullet_summary(text: str, max_points: int = 4) -> list[str]:
    return extract_key_points(text, max_points=max_points)


def detect_document_type(text: str, filename: str = "") -> str:
    combined = f"{filename} {text}".lower()
    scores = {
        doc_type: sum(1 for marker in markers if marker in combined)
        for doc_type, markers in DOCUMENT_TYPE_RULES.items()
    }
    best_type = max(scores, key=scores.get)
    return best_type if scores[best_type] else "general document"


def extract_dates(text: str, max_dates: int = 8) -> list[str]:
    dates = []
    seen = set()
    for match in DATE_PATTERN.finditer(text):
        value = match.group(0).strip()
        key = value.lower()
        if key not in seen:
            dates.append(value)
            seen.add(key)
        if len(dates) >= max_dates:
            break
    return dates


def extract_action_items(text: str, max_items: int = 5) -> list[str]:
    sentences = split_into_sentences(text)
    items = []
    for sentence in sentences:
        lowered = sentence.lower()
        if any(marker in lowered for marker in ACTION_MARKERS):
            items.append(sentence)
        if len(items) >= max_items:
            break
    return items


def build_suggested_questions(
    document_type: str,
    keywords: list[str],
    dates: list[str],
    action_items: list[str],
) -> list[str]:
    questions = [
        "What are the most important points in this document?",
        "What should I pay attention to before using this document?",
    ]

    if document_type != "general document":
        questions.append(f"What makes this look like a {document_type}?")
    if dates:
        questions.append("Which dates or deadlines are mentioned?")
    if action_items:
        questions.append("What actions or next steps are required?")
    if keywords:
        questions.append(f"What does the document say about {keywords[0]}?")

    return questions[:5]


def build_document_insights(text: str, filename: str = "") -> dict:
    text = normalize_text(text)

    word_count = calculate_word_count(text)
    reading_time = estimate_reading_time_minutes(word_count)
    summary_short = build_short_summary(text)
    key_points = extract_key_points(text)
    bullet_summary = build_bullet_summary(text)
    keywords = extract_keywords(text)
    document_type = detect_document_type(text, filename)
    dates = extract_dates(text)
    action_items = extract_action_items(text)
    suggested_questions = build_suggested_questions(
        document_type,
        keywords,
        dates,
        action_items,
    )

    return {
        "word_count": word_count,
        "estimated_reading_time_min": reading_time,
        "summary_short": summary_short,
        "key_points": "\n".join(key_points),
        "bullet_summary": "\n".join(bullet_summary),
        "keywords": ", ".join(keywords),
        "document_type": document_type,
        "detected_dates": "\n".join(dates),
        "action_items": "\n".join(action_items),
        "suggested_questions": "\n".join(suggested_questions),
    }
