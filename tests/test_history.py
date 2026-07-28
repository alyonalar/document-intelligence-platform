from app.services.history import deserialize_sources, serialize_document_ids, serialize_sources


def test_serialize_document_ids_adds_boundaries():
    assert serialize_document_ids([1, 10, 25]) == ",1,10,25,"


def test_serialize_document_ids_returns_empty_string_for_empty_list():
    assert serialize_document_ids([]) == ""


def test_serialize_sources_round_trip():
    sources = [{"filename": "doc.txt", "chunk_id": 1, "text": "Evidence"}]

    encoded = serialize_sources(sources)

    assert deserialize_sources(encoded) == sources
