from app.services.summarizer import (
    build_document_insights,
    calculate_word_count,
    extract_keywords,
    split_into_sentences,
)


def test_split_into_sentences_handles_newlines_and_punctuation():
    sentences = split_into_sentences("Первое предложение. Второе?\nТретье!")

    assert sentences == ["Первое предложение.", "Второе?", "Третье!"]


def test_calculate_word_count_supports_cyrillic():
    assert calculate_word_count("Привет мир test") == 3


def test_extract_keywords_filters_common_stopwords():
    keywords = extract_keywords("Документ содержит важный план и важный анализ проекта.")

    assert "важный" in keywords
    assert "план" in keywords
    assert "и" not in keywords


def test_build_document_insights_returns_expected_shape():
    insights = build_document_insights(
        "Документ описывает проект. Проект помогает анализировать документы."
    )

    assert insights["word_count"] > 0
    assert insights["estimated_reading_time_min"] >= 1
    assert "проект" in insights["keywords"]


def test_build_document_insights_detects_type_dates_actions_and_questions():
    insights = build_document_insights(
        "Meeting agenda for product launch. Deadline is 2026-07-15. "
        "Team needs to prepare the demo before July 20, 2026.",
        "meeting-notes.txt",
    )

    assert insights["document_type"] == "meeting notes"
    assert "2026-07-15" in insights["detected_dates"]
    assert "July 20, 2026" in insights["detected_dates"]
    assert "needs to prepare" in insights["action_items"]
    assert "Which dates or deadlines are mentioned?" in insights["suggested_questions"]
