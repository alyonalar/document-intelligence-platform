from app.services import vector_store


def test_semantic_search_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(vector_store.settings, "semantic_search_enabled", False)
    monkeypatch.setattr(vector_store.settings, "openai_api_key", None)

    assert vector_store.semantic_search_available() is False


def test_search_document_chunks_returns_empty_when_disabled(monkeypatch):
    monkeypatch.setattr(vector_store.settings, "semantic_search_enabled", False)
    monkeypatch.setattr(vector_store.settings, "openai_api_key", None)

    assert vector_store.search_document_chunks("question", document_ids=[1]) == []


def test_reindex_document_chunks_returns_zero_when_disabled(monkeypatch):
    monkeypatch.setattr(vector_store.settings, "semantic_search_enabled", False)
    monkeypatch.setattr(vector_store.settings, "openai_api_key", None)

    document = type("DocumentStub", (), {"id": 1, "raw_text": "content"})()

    assert vector_store.reindex_document_chunks(document) == 0
