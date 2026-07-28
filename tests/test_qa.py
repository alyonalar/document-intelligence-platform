from app.services.qa import answer_question, find_relevant_chunks, tokenize


def test_tokenize_filters_stopwords_and_short_words():
    tokens = tokenize("Что это за API и как он работает?")

    assert "api" in tokens
    assert "это" not in tokens


def test_find_relevant_chunks_returns_matching_chunk():
    text = "Alpha topic is unrelated. Billing policy requires approval."
    chunks = find_relevant_chunks(text, "billing approval", top_k=1)

    assert len(chunks) == 1
    assert "Billing policy" in chunks[0]


def test_answer_question_returns_evidence_for_matching_text():
    result = answer_question(
        "Проект использует FastAPI для обработки документов.",
        "Что использует проект?",
    )

    assert "FastAPI" in result["answer"]
    assert result["evidence"]
    assert result["relevant_chunks"][0]["chunk_id"] == 1
