from openai import OpenAI

from app.core.config import settings
from app.services.qa import find_relevant_chunk_matches
from app.services.vector_store import search_document_chunks


def build_document_prompt(context_blocks: list[dict], question: str) -> str:
    context_text = "\n\n".join([f"[Chunk {item['id']}]\n{item['text']}" for item in context_blocks])

    return f"""
You are a helpful document intelligence assistant.

Answer the user's question only using the provided context.
If the answer is not clearly present in the context, say that the answer was not found in the document.
When possible, mention which chunk(s) support the answer, for example: [Chunk 1].
Do not invent facts.
Be concise and grounded.

Context:
{context_text}

Question:
{question}
""".strip()


def ask_llm_about_document(
    document_text: str, question: str, document_id: int | None = None
) -> dict:
    if not settings.llm_enabled:
        return {
            "enabled": False,
            "answer": "LLM mode is disabled.",
            "model": None,
            "relevant_chunks": [],
        }

    if not settings.openai_api_key:
        return {
            "enabled": False,
            "answer": "OPENAI_API_KEY is not configured.",
            "model": None,
            "relevant_chunks": [],
        }

    semantic_chunks = []
    if document_id is not None:
        semantic_chunks = search_document_chunks(question, document_ids=[document_id], top_k=3)

    if semantic_chunks:
        context_blocks = [
            {
                "id": item["chunk_id"] or idx,
                "chunk_id": item["chunk_id"] or idx,
                "text": item["text"],
            }
            for idx, item in enumerate(semantic_chunks, start=1)
        ]
    else:
        context_blocks = [
            {
                "id": chunk["chunk_id"],
                "chunk_id": chunk["chunk_id"],
                "text": chunk["text"],
            }
            for chunk in find_relevant_chunk_matches(document_text, question, top_k=3)
        ]

    if not context_blocks:
        context_blocks = [{"id": 1, "chunk_id": 1, "text": document_text[:6000]}]

    client = OpenAI(api_key=settings.openai_api_key)

    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {
                "role": "system",
                "content": "You answer questions about documents using only the provided context.",
            },
            {
                "role": "user",
                "content": build_document_prompt(context_blocks, question),
            },
        ],
        temperature=0.2,
    )

    answer = response.choices[0].message.content if response.choices else "No answer returned."

    return {
        "enabled": True,
        "answer": answer,
        "model": settings.openai_model,
        "relevant_chunks": context_blocks,
        "retrieval": "semantic" if semantic_chunks else "keyword",
    }


def build_summary_prompt(document_text: str) -> str:
    return f"""
Ты помощник для суммаризации документов.

Сделай краткое саммари только по тексту ниже.
Пиши ответ на русском языке.
Не добавляй факты, которых нет в тексте.
Не используй английский язык, кроме общепринятых технических терминов при необходимости.

Верни:
1. Краткий обзор в 2-4 предложения
2. 3 пункта с самыми важными идеями
3. Короткую пометку, если текст неполный или неоднозначный

Документ:
\"\"\"
{document_text[:12000]}
\"\"\"
""".strip()


def generate_llm_summary(document_text: str) -> dict:
    if not settings.llm_enabled:
        return {
            "enabled": False,
            "summary": "LLM mode is disabled.",
            "model": None,
        }

    if not settings.openai_api_key:
        return {
            "enabled": False,
            "summary": "OPENAI_API_KEY is not configured.",
            "model": None,
        }

    client = OpenAI(api_key=settings.openai_api_key)

    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {
                "role": "system",
                "content": "Ты отвечаешь на русском языке и используешь только предоставленный контекст.",
            },
            {"role": "user", "content": build_summary_prompt(document_text)},
        ],
        temperature=0.2,
    )

    summary = response.choices[0].message.content if response.choices else "No summary returned."

    return {
        "enabled": True,
        "summary": summary,
        "model": settings.openai_model,
    }
