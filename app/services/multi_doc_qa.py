import logging
from pathlib import Path

from openai import OpenAI

from app.core.config import settings
from app.services.chunking import chunk_pages, chunk_text
from app.services.parsers import parse_pdf_pages
from app.services.qa import score_text, tokenize
from app.services.vector_store import search_document_chunks

logger = logging.getLogger(__name__)


def build_document_chunk_records(document) -> list[dict]:
    file_path = Path(document.stored_path)
    if document.file_type == "pdf" and file_path.exists():
        try:
            page_chunks = chunk_pages(parse_pdf_pages(str(file_path)), chunk_size=800, overlap=120)
            if page_chunks:
                return page_chunks
        except Exception as e:
            logger.warning(
                "Could not parse PDF chunks for workspace document %s: %s", document.id, e
            )

    return [
        {"chunk_id": idx, "page_number": None, "text": chunk}
        for idx, chunk in enumerate(
            chunk_text(document.raw_text or "", chunk_size=800, overlap=120),
            start=1,
        )
    ]


def retrieve_relevant_chunks(documents: list, question: str, top_k: int = 5) -> list[dict]:
    document_ids = [document.id for document in documents if document.id is not None]
    semantic_chunks = search_document_chunks(question, document_ids=document_ids, top_k=top_k)
    if semantic_chunks:
        return semantic_chunks

    query_tokens = tokenize(question)
    if not query_tokens:
        return []

    ranked_chunks = []

    for document in documents:
        for chunk in build_document_chunk_records(document):
            score = score_text(query_tokens, chunk["text"])
            if score > 0:
                ranked_chunks.append(
                    {
                        "document_id": document.id,
                        "filename": document.filename,
                        "chunk_id": chunk["chunk_id"],
                        "page_number": chunk.get("page_number"),
                        "text": chunk["text"],
                        "score": score,
                    }
                )

    ranked_chunks.sort(key=lambda item: item["score"], reverse=True)
    return ranked_chunks[:top_k]


def build_multi_doc_prompt(chunks: list[dict], question: str) -> str:
    context_parts = []

    for i, chunk in enumerate(chunks, start=1):
        page = f"\nPage: {chunk['page_number']}" if chunk.get("page_number") else ""
        context_parts.append(
            f"[Source {i}]\n"
            f"File: {chunk['filename']}\n"
            f"Chunk: {chunk['chunk_id']}"
            f"{page}\n"
            f"Text: {chunk['text']}"
        )

    context = "\n\n".join(context_parts)

    return f"""
Ты помощник по анализу документов.

Ответь на вопрос только на основе контекста ниже.
Пиши ответ только на русском языке.
Если ответа в контексте нет, так и скажи.
Для важных утверждений указывай источники в формате [Source 1], [Source 2].
Не придумывай факты.

Контекст:
{context}

Вопрос:
{question}
""".strip()


def ask_llm_across_documents(documents: list, question: str) -> dict:
    if not settings.llm_enabled:
        return {
            "answer": "LLM mode is disabled.",
            "sources": [],
            "model": None,
        }

    if not settings.openai_api_key:
        return {
            "answer": "OPENAI_API_KEY is not configured.",
            "sources": [],
            "model": None,
        }

    relevant_chunks = retrieve_relevant_chunks(documents, question, top_k=5)

    if not relevant_chunks:
        return {
            "answer": "Не удалось найти релевантные фрагменты в выбранных документах.",
            "sources": [],
            "model": settings.openai_model,
        }

    client = OpenAI(api_key=settings.openai_api_key)

    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {
                "role": "system",
                "content": "Ты отвечаешь на русском языке и используешь только предоставленный контекст из документов.",
            },
            {
                "role": "user",
                "content": build_multi_doc_prompt(relevant_chunks, question),
            },
        ],
        temperature=0.2,
    )

    answer = response.choices[0].message.content if response.choices else "Ответ не получен."

    sources = []
    for i, chunk in enumerate(relevant_chunks, start=1):
        sources.append(
            {
                "source_id": i,
                "document_id": chunk["document_id"],
                "filename": chunk["filename"],
                "chunk_id": chunk["chunk_id"],
                "page_number": chunk.get("page_number"),
                "text": chunk["text"],
            }
        )

    return {
        "answer": answer,
        "sources": sources,
        "model": settings.openai_model,
    }
