from fastapi import APIRouter, Form, Request, status
from fastapi.responses import RedirectResponse
from sqlmodel import Session

from app.db.engine import engine
from app.db.models import Document
from app.dependencies import templates
from app.services.document_compare import compare_documents
from app.services.document_diff import build_document_diff
from app.services.history import list_recent_interactions, save_qa_interaction
from app.services.multi_doc_qa import ask_llm_across_documents

router = APIRouter()


def get_documents_by_ids(document_ids: list[int]) -> list[Document]:
    with Session(engine) as session:
        documents = []
        for doc_id in document_ids:
            document = session.get(Document, doc_id)
            if document:
                documents.append(document)
        return documents


@router.post("/workspace")
def open_workspace(document_ids: list[int] = Form(default=[])):
    if not document_ids:
        return RedirectResponse(
            url="/?workspace_error=Select at least one document.",
            status_code=status.HTTP_303_SEE_OTHER,
        )
    query_string = "&".join([f"document_ids={doc_id}" for doc_id in document_ids])
    return RedirectResponse(
        url=f"/workspace?{query_string}",
        status_code=status.HTTP_303_SEE_OTHER,
    )


@router.get("/workspace")
def workspace(request: Request, question: str = ""):
    raw_ids = request.query_params.getlist("document_ids")
    document_ids = [int(doc_id) for doc_id in raw_ids if str(doc_id).isdigit()]
    documents = get_documents_by_ids(document_ids)

    with Session(engine) as session:
        history = list_recent_interactions(session, limit=6)

    return templates.TemplateResponse(
        request=request,
        name="workspace.html",
        context={
            "request": request,
            "documents": documents,
            "document_ids": document_ids,
            "question": question,
            "result": None,
            "history": history,
        },
    )


@router.get("/workspace/ask")
def workspace_ask(request: Request, question: str = ""):
    raw_ids = request.query_params.getlist("document_ids")
    document_ids = [int(doc_id) for doc_id in raw_ids if str(doc_id).isdigit()]
    documents = get_documents_by_ids(document_ids)

    result = None
    if documents and question.strip():
        result = ask_llm_across_documents(documents, question)
        with Session(engine) as session:
            save_qa_interaction(
                session=session,
                scope="workspace",
                question=question,
                answer=result.get("answer", ""),
                document_ids=document_ids,
                model=result.get("model"),
                retrieval="semantic_or_keyword",
                sources=result.get("sources"),
            )

    with Session(engine) as session:
        history = list_recent_interactions(session, limit=6)

    return templates.TemplateResponse(
        request=request,
        name="workspace.html",
        context={
            "request": request,
            "documents": documents,
            "document_ids": document_ids,
            "question": question,
            "result": result,
            "history": history,
        },
    )


@router.get("/workspace/compare")
def workspace_compare(request: Request):
    raw_ids = request.query_params.getlist("document_ids")
    document_ids = [int(doc_id) for doc_id in raw_ids if str(doc_id).isdigit()]
    documents = get_documents_by_ids(document_ids)

    if len(documents) == 2:
        diff_result = build_document_diff(
            doc1_name=documents[0].filename,
            doc1_text=documents[0].raw_text or "",
            doc2_name=documents[1].filename,
            doc2_text=documents[1].raw_text or "",
        )
        comparison_result = compare_documents(
            doc1_name=documents[0].filename,
            doc1_text=documents[0].raw_text or "",
            doc2_name=documents[1].filename,
            doc2_text=documents[1].raw_text or "",
        )
    else:
        diff_result = None
        comparison_result = {
            "answer": "Для сравнения нужно выбрать ровно 2 документа.",
            "model": None,
            "doc1_name": None,
            "doc2_name": None,
        }

    return templates.TemplateResponse(
        request=request,
        name="workspace_compare.html",
        context={
            "request": request,
            "documents": documents,
            "document_ids": document_ids,
            "result": comparison_result,
            "diff_result": diff_result,
        },
    )
