import logging

from app.core.config import settings
from app.services.chunking import chunk_pages, chunk_text
from app.services.parsers import parse_pdf_pages
from app.services.runtime_settings import semantic_search_configured, semantic_search_enabled

COLLECTION_NAME = "document_chunks"
logger = logging.getLogger(__name__)


def semantic_search_available() -> bool:
    return bool(semantic_search_enabled() and semantic_search_configured())


def get_chroma_collection():
    import chromadb

    client = chromadb.PersistentClient(path=settings.chroma_dir)
    return client.get_or_create_collection(name=COLLECTION_NAME)


def build_embeddings(texts: list[str]) -> list[list[float]]:
    from openai import OpenAI

    client = OpenAI(api_key=settings.openai_api_key)
    response = client.embeddings.create(
        model=settings.openai_embedding_model,
        input=texts,
    )

    return [item.embedding for item in response.data]


def index_document_chunks(document) -> int:
    if not semantic_search_available():
        return 0

    chunk_records = build_index_chunk_records(document)
    chunks = [item["text"] for item in chunk_records]
    if not chunks:
        return 0

    try:
        collection = get_chroma_collection()
        embeddings = build_embeddings(chunks)

        ids = [f"doc:{document.id}:chunk:{item['chunk_id']}" for item in chunk_records]
        metadatas = [
            {
                "document_id": document.id,
                "filename": document.filename,
                "chunk_id": item["chunk_id"],
                "page_number": item.get("page_number"),
            }
            for item in chunk_records
        ]

        collection.upsert(
            ids=ids,
            documents=chunks,
            embeddings=embeddings,
            metadatas=metadatas,
        )
    except Exception as e:
        logger.warning(
            "Could not index semantic chunks for document %s: %s", getattr(document, "id", None), e
        )
        return 0

    return len(chunks)


def build_index_chunk_records(document) -> list[dict]:
    if document.file_type == "pdf":
        try:
            page_chunks = chunk_pages(
                parse_pdf_pages(document.stored_path),
                chunk_size=900,
                overlap=150,
            )
            if page_chunks:
                return page_chunks
        except Exception as e:
            logger.warning(
                "Could not build PDF index chunks for document %s: %s",
                getattr(document, "id", None),
                e,
            )

    return [
        {"chunk_id": idx, "text": chunk, "page_number": None}
        for idx, chunk in enumerate(
            chunk_text(document.raw_text or "", chunk_size=900, overlap=150),
            start=1,
        )
    ]


def reindex_document_chunks(document) -> int:
    if document.id is None:
        return 0

    delete_document_chunks(document.id)
    return index_document_chunks(document)


def delete_document_chunks(document_id: int) -> None:
    if not semantic_search_available():
        return

    try:
        collection = get_chroma_collection()
        collection.delete(where={"document_id": document_id})
    except Exception as e:
        logger.warning("Could not delete semantic chunks for document %s: %s", document_id, e)
        return


def search_document_chunks(
    question: str,
    document_ids: list[int] | None = None,
    top_k: int = 5,
) -> list[dict]:
    if not semantic_search_available() or not question.strip():
        return []

    try:
        collection = get_chroma_collection()
        query_embedding = build_embeddings([question])[0]

        where = None
        if document_ids:
            where = {"document_id": {"$in": document_ids}}

        result = collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k,
            where=where,
        )
    except Exception as e:
        logger.warning("Semantic search failed for document_ids=%s: %s", document_ids, e)
        return []

    documents = result.get("documents", [[]])[0]
    metadatas = result.get("metadatas", [[]])[0]
    distances = result.get("distances", [[]])[0]

    chunks = []
    for text, metadata, distance in zip(
        documents,
        metadatas,
        distances,
        strict=False,
    ):
        chunks.append(
            {
                "document_id": metadata.get("document_id"),
                "filename": metadata.get("filename"),
                "chunk_id": metadata.get("chunk_id"),
                "page_number": metadata.get("page_number"),
                "text": text,
                "score": distance,
            }
        )

    return chunks
