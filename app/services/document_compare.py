from openai import OpenAI

from app.core.config import settings


def build_compare_prompt(doc1_name: str, doc1_text: str, doc2_name: str, doc2_text: str) -> str:
    return f"""
Ты помощник для сравнения документов.

Сравни два документа и покажи:
1. Основные различия: что изменилось, что добавилось, что убрали
2. Основные сходства: общие темы, утверждения и идеи
3. Ключевые темы, которые повторяются в обоих документах
4. Потенциальные противоречия или расхождения

Пиши ответ только на русском языке.
Не придумывай факты, которых нет в текстах.
Будь конкретным и структурированным.

Документ 1: {doc1_name}
\"\"\"
{doc1_text[:8000]}
\"\"\"

Документ 2: {doc2_name}
\"\"\"
{doc2_text[:8000]}
\"\"\"
""".strip()


def compare_documents(doc1_name: str, doc1_text: str, doc2_name: str, doc2_text: str) -> dict:
    if not settings.llm_enabled:
        return {
            "answer": "LLM mode is disabled.",
            "model": None,
        }

    if not settings.openai_api_key:
        return {
            "answer": "OPENAI_API_KEY is not configured.",
            "model": None,
        }

    client = OpenAI(api_key=settings.openai_api_key)

    response = client.chat.completions.create(
        model=settings.openai_model,
        messages=[
            {
                "role": "system",
                "content": "Ты отвечаешь на русском языке и используешь только предоставленные тексты документов.",
            },
            {
                "role": "user",
                "content": build_compare_prompt(doc1_name, doc1_text, doc2_name, doc2_text),
            },
        ],
        temperature=0.2,
    )

    answer = response.choices[0].message.content if response.choices else "Анализ не получен."

    return {
        "answer": answer,
        "model": settings.openai_model,
        "doc1_name": doc1_name,
        "doc2_name": doc2_name,
    }
