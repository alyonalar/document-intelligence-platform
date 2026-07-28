from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, HTTPException, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from app.db.engine import get_session
from app.db.models import Collection, CollectionDocumentLink, Document
from app.dependencies import templates
from app.services.exporter import (
    build_collection_docx,
    build_collection_markdown,
    build_collection_pdf,
)
from app.web.responses import docx_attachment, markdown_attachment, pdf_attachment

router = APIRouter(prefix="/collections", tags=["collections"])
COLLECTION_EXPORT_SECTIONS = {"overview", "documents", "summaries"}


def redirect_home(request: Request, **query_params):
    fragment = query_params.pop("fragment", "")
    query_string = urlencode(
        {key: value for key, value in query_params.items() if value is not None}
    )
    url = str(request.url_for("home"))
    if query_string:
        url = f"{url}?{query_string}"
    if fragment:
        url = f"{url}#{fragment}"
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


def redirect_collection(request: Request, collection_id: int, **query_params):
    query_string = urlencode(
        {key: value for key, value in query_params.items() if value is not None}
    )
    url = str(request.url_for("view_collection", collection_id=collection_id))
    if query_string:
        url = f"{url}?{query_string}"
    return RedirectResponse(url=url, status_code=status.HTTP_303_SEE_OTHER)


def normalize_export_sections(sections: list[str] | None) -> set[str] | None:
    if not sections:
        return None

    normalized = {
        section.strip().lower()
        for value in sections
        for section in value.split(",")
        if section.strip()
    }
    selected = normalized & COLLECTION_EXPORT_SECTIONS
    return selected or None


def get_collection_documents(session: Session, collection_id: int) -> list[Document]:
    links = session.exec(
        select(CollectionDocumentLink).where(CollectionDocumentLink.collection_id == collection_id)
    ).all()
    document_ids = [link.document_id for link in links if link.document_id]
    if not document_ids:
        return []

    return session.exec(
        select(Document).where(Document.id.in_(document_ids)).order_by(Document.created_at.desc())
    ).all()


@router.post("/create")
def create_collection(
    request: Request,
    name: str = Form(""),
    description: str = Form(""),
    session: Session = Depends(get_session),
):
    name = name.strip()
    description = description.strip()

    if not name:
        return redirect_home(
            request, collection_error="Collection name is required.", fragment="collections"
        )

    existing = session.exec(select(Collection).where(Collection.name == name)).first()
    if existing:
        return redirect_home(request, collection_error=f"Collection already exists: {name}")

    collection = Collection(name=name, description=description or None)
    session.add(collection)
    session.commit()
    session.refresh(collection)

    return redirect_home(request, collection_notice=f"Created collection: {collection.name}")


@router.get("/{collection_id}/export.md")
def export_collection_markdown(
    collection_id: int,
    sections: list[str] | None = Query(default=None),
    session: Session = Depends(get_session),
):
    collection = session.get(Collection, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    documents = get_collection_documents(session, collection_id)
    content = build_collection_markdown(
        collection,
        documents,
        sections=normalize_export_sections(sections),
    )
    return markdown_attachment(content, f"collection-{collection_id}.md")


@router.get("/{collection_id}/export.docx")
def export_collection_docx(
    collection_id: int,
    sections: list[str] | None = Query(default=None),
    session: Session = Depends(get_session),
):
    collection = session.get(Collection, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    documents = get_collection_documents(session, collection_id)
    buffer = build_collection_docx(
        collection,
        documents,
        sections=normalize_export_sections(sections),
    )
    return docx_attachment(buffer, f"collection-{collection_id}.docx")


@router.get("/{collection_id}/export.pdf")
def export_collection_pdf(
    collection_id: int,
    sections: list[str] | None = Query(default=None),
    session: Session = Depends(get_session),
):
    collection = session.get(Collection, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    documents = get_collection_documents(session, collection_id)
    buffer = build_collection_pdf(
        collection,
        documents,
        sections=normalize_export_sections(sections),
    )
    return pdf_attachment(buffer, f"collection-{collection_id}.pdf")


@router.get("/{collection_id}", name="view_collection")
def collection_detail(
    request: Request,
    collection_id: int,
    collection_notice: str = "",
    collection_error: str = "",
    session: Session = Depends(get_session),
):
    collection = session.get(Collection, collection_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    documents = get_collection_documents(session, collection_id)
    stats = {
        "total_documents": len(documents),
        "total_words": sum(document.word_count for document in documents),
        "total_size": sum(document.file_size for document in documents),
        "avg_reading_time": round(
            sum(document.estimated_reading_time_min for document in documents) / len(documents)
        )
        if documents
        else 0,
    }

    return templates.TemplateResponse(
        request=request,
        name="collection_detail.html",
        context={
            "request": request,
            "collection": collection,
            "documents": documents,
            "stats": stats,
            "collection_notice": collection_notice,
            "collection_error": collection_error,
        },
    )


@router.post("/{collection_id}/update")
def update_collection(
    request: Request,
    collection_id: int,
    name: str = Form(...),
    description: str = Form(""),
    session: Session = Depends(get_session),
):
    collection = session.get(Collection, collection_id)
    if not collection:
        return redirect_home(request, collection_error="Collection not found.")

    name = name.strip()
    description = description.strip()

    if not name:
        return redirect_collection(
            request,
            collection_id,
            collection_error="Collection name is required.",
        )

    existing = session.exec(
        select(Collection).where(Collection.name == name, Collection.id != collection_id)
    ).first()
    if existing:
        return redirect_collection(
            request,
            collection_id,
            collection_error=f"Collection already exists: {name}",
        )

    collection.name = name
    collection.description = description or None
    session.add(collection)
    session.commit()

    return redirect_collection(
        request,
        collection_id,
        collection_notice=f"Updated collection: {collection.name}",
    )


@router.post("/{collection_id}/remove-document")
def remove_document_from_collection(
    request: Request,
    collection_id: int,
    document_id: int = Form(...),
    session: Session = Depends(get_session),
):
    link = session.get(
        CollectionDocumentLink,
        (collection_id, document_id),
    )
    if link:
        session.delete(link)
        session.commit()

    return RedirectResponse(
        url=request.url_for("view_collection", collection_id=collection_id),
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.post("/{collection_id}/delete")
def delete_collection(
    request: Request,
    collection_id: int,
    session: Session = Depends(get_session),
):
    collection = session.get(Collection, collection_id)
    if not collection:
        return redirect_home(request, collection_error="Collection not found.")

    links = session.exec(
        select(CollectionDocumentLink).where(CollectionDocumentLink.collection_id == collection_id)
    ).all()
    for link in links:
        session.delete(link)

    session.delete(collection)
    session.commit()

    return redirect_home(
        request,
        collection_notice=f"Deleted collection: {collection.name}",
        fragment="collections",
    )


@router.post("/add-documents")
def add_documents_to_collection(
    request: Request,
    collection_id: int = Form(...),
    document_ids: list[int] = Form(default=[]),
    session: Session = Depends(get_session),
):
    collection = session.get(Collection, collection_id)
    if not collection:
        return redirect_home(request, collection_error="Collection not found.")

    if not document_ids:
        return redirect_home(
            request, collection_error="Select at least one document.", fragment="collections"
        )

    added = 0
    for document_id in document_ids:
        document = session.get(Document, document_id)
        if not document:
            continue

        existing = session.exec(
            select(CollectionDocumentLink).where(
                CollectionDocumentLink.collection_id == collection_id,
                CollectionDocumentLink.document_id == document_id,
            )
        ).first()
        if existing:
            continue

        session.add(
            CollectionDocumentLink(
                collection_id=collection_id,
                document_id=document_id,
            )
        )
        added += 1

    session.commit()

    return redirect_home(
        request,
        collection_notice=f"Added {added} document(s) to {collection.name}.",
        fragment="collections",
    )
