import re
from collections import Counter

from app.services.chunking import chunk_text

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
    "who",
    "what",
    "when",
    "where",
    "why",
    "how",
}


def split_into_sentences(text: str) -> list[str]:
    text = text.strip()
    if not text:
        return []

    sentences = re.split(r"(?<=[.!?])\s+|\n+", text)
    return [s.strip() for s in sentences if s.strip()]


def tokenize(text: str) -> list[str]:
    words = re.findall(r"\b[\w-]+\b", text.lower(), flags=re.UNICODE)
    return [w for w in words if len(w) > 2 and w not in STOPWORDS and not w.isdigit()]


def score_text(query_tokens: list[str], text: str) -> int:
    text_tokens = tokenize(text)
    if not text_tokens:
        return 0

    token_counts = Counter(text_tokens)
    score = 0

    for token in query_tokens:
        score += token_counts[token]

    return score


def find_relevant_chunk_matches(text: str, question: str, top_k: int = 3) -> list[dict]:
    query_tokens = tokenize(question)
    chunks = chunk_text(text, chunk_size=800, overlap=120)

    if not query_tokens or not chunks:
        return []

    scored = []
    for index, chunk in enumerate(chunks, start=1):
        score = score_text(query_tokens, chunk)
        if score > 0:
            scored.append(
                {
                    "id": index,
                    "chunk_id": index,
                    "text": chunk,
                    "score": score,
                }
            )

    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:top_k]


def find_relevant_chunks(text: str, question: str, top_k: int = 3) -> list[str]:
    return [item["text"] for item in find_relevant_chunk_matches(text, question, top_k)]


def find_relevant_sentences_from_chunks(
    chunks: list[str], question: str, top_k: int = 3
) -> list[str]:
    query_tokens = tokenize(question)
    if not query_tokens:
        return []

    scored = []
    for chunk in chunks:
        for sentence in split_into_sentences(chunk):
            score = score_text(query_tokens, sentence)
            if score > 0:
                scored.append((sentence, score))

    scored.sort(key=lambda x: x[1], reverse=True)

    results = []
    seen = set()
    for sentence, _ in scored:
        if sentence not in seen:
            results.append(sentence)
            seen.add(sentence)
        if len(results) >= top_k:
            break

    return results


def answer_question(text: str, question: str) -> dict:
    question = question.strip()

    if not question:
        return {
            "question": "",
            "answer": "Please enter a question.",
            "evidence": [],
            "relevant_chunks": [],
        }

    if not text or not text.strip():
        return {
            "question": question,
            "answer": "This document has no extracted text to search through.",
            "evidence": [],
            "relevant_chunks": [],
        }

    relevant_chunks = find_relevant_chunk_matches(text, question, top_k=3)
    relevant_sentences = find_relevant_sentences_from_chunks(
        [chunk["text"] for chunk in relevant_chunks],
        question,
        top_k=3,
    )

    if not relevant_chunks and not relevant_sentences:
        return {
            "question": question,
            "answer": "I couldn't find a clear answer in this document.",
            "evidence": [],
            "relevant_chunks": [],
        }

    answer = relevant_sentences[0] if relevant_sentences else relevant_chunks[0]["text"]

    return {
        "question": question,
        "answer": answer,
        "evidence": relevant_sentences,
        "relevant_chunks": relevant_chunks,
    }
