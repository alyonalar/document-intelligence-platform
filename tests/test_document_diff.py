from app.services.document_diff import build_document_diff, jaccard_similarity


def test_jaccard_similarity_handles_sets():
    assert jaccard_similarity({"a", "b"}, {"b", "c"}) == 0.333


def test_build_document_diff_returns_keyword_overlap():
    diff = build_document_diff(
        "one.txt",
        "Billing approval policy and project notes.",
        "two.txt",
        "Billing approval workflow and client notes.",
    )

    assert diff["doc1_name"] == "one.txt"
    assert diff["doc2_name"] == "two.txt"
    assert "billing" in diff["common_keywords"]
    assert diff["keyword_similarity"] > 0
