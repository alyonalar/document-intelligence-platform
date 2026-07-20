import re

CATEGORY_RULES = {
    "documentation": [
        "api",
        "endpoint",
        "request",
        "response",
        "function",
        "module",
        "documentation",
        "readme",
        "install",
        "usage",
        "example",
        "config",
    ],
    "notes": [
        "note",
        "notes",
        "summary",
        "idea",
        "draft",
        "thought",
        "plan",
        "набросок",
        "заметка",
        "конспект",
        "план",
        "идея",
    ],
    "education": [
        "exam",
        "lesson",
        "course",
        "lecture",
        "study",
        "topic",
        "question",
        "answer",
        "chapter",
        "education",
        "training",
        "экзамен",
        "лекция",
        "тема",
        "обучение",
        "глава",
        "вопрос",
    ],
    "fiction": [
        "chapter",
        "prologue",
        "character",
        "story",
        "novel",
        "scene",
        "dialogue",
        "hero",
        "герой",
        "пролог",
        "глава",
        "история",
    ],
}


def tokenize(text: str) -> list[str]:
    return re.findall(r"\b[\w-]+\b", text.lower(), flags=re.UNICODE)


def classify_document(text: str, filename: str = "") -> str:
    combined = f"{filename} {text}".lower()
    tokens = tokenize(combined)

    if not tokens:
        return "uncategorized"

    scores = {}

    for category, keywords in CATEGORY_RULES.items():
        score = sum(1 for token in tokens if token in keywords)
        scores[category] = score

    best_category = max(scores, key=scores.get)

    if scores[best_category] == 0:
        return "general"

    return best_category
