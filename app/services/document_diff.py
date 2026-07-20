from app.services.document_structure import build_document_structure
from app.services.summarizer import extract_keywords


def jaccard_similarity(left: set[str], right: set[str]) -> float:
    if not left and not right:
        return 1.0
    if not left or not right:
        return 0.0
    return round(len(left & right) / len(left | right), 3)


def build_document_diff(doc1_name: str, doc1_text: str, doc2_name: str, doc2_text: str) -> dict:
    doc1_keywords = set(extract_keywords(doc1_text, max_keywords=25))
    doc2_keywords = set(extract_keywords(doc2_text, max_keywords=25))

    doc1_words = len(doc1_text.split())
    doc2_words = len(doc2_text.split())

    doc1_structure = build_document_structure(doc1_text, "txt", doc1_words)
    doc2_structure = build_document_structure(doc2_text, "txt", doc2_words)

    return {
        "doc1_name": doc1_name,
        "doc2_name": doc2_name,
        "word_count_delta": doc2_words - doc1_words,
        "keyword_similarity": jaccard_similarity(doc1_keywords, doc2_keywords),
        "common_keywords": sorted(doc1_keywords & doc2_keywords),
        "only_in_doc1_keywords": sorted(doc1_keywords - doc2_keywords),
        "only_in_doc2_keywords": sorted(doc2_keywords - doc1_keywords),
        "doc1_sections": doc1_structure["sections"],
        "doc2_sections": doc2_structure["sections"],
        "doc1_preview": doc1_structure["preview_blocks"][:2],
        "doc2_preview": doc2_structure["preview_blocks"][:2],
    }
