from app.services.classifier import classify_document


def test_classify_document_detects_education_from_russian_text():
    category = classify_document("Тема экзамена и вопросы для обучения", "program.docx")

    assert category == "education"


def test_classify_document_returns_general_when_no_rules_match():
    category = classify_document("Random unrelated content", "file.txt")

    assert category == "general"


def test_classify_document_returns_uncategorized_for_empty_input():
    category = classify_document("", "")

    assert category == "uncategorized"
