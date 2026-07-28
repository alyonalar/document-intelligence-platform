from sqlmodel import Session, select

from app.db.models import Document, utc_now
from app.services.entity_extraction_service import extract_entities
from app.services.obligation_service import extract_obligations
from app.services.relationship_graph_service import build_relations_for_document
from app.services.risk_detection_service import detect_risks


def process_document_intelligence(session: Session, document: Document) -> dict:
    if document.id is None:
        return {"success": False, "message": "Document is not persisted."}
    if not document.raw_text:
        document.intelligence_status = "error"
        document.intelligence_error = "No extracted text is available for intelligence processing."
        session.add(document)
        session.commit()
        return {"success": False, "message": document.intelligence_error}

    document.intelligence_status = "processing"
    document.intelligence_error = None
    session.add(document)
    session.commit()
    session.refresh(document)

    try:
        entities = extract_entities(session, document.id, commit=False)
        obligations = extract_obligations(session, document.id, commit=False)
        risks = detect_risks(session, document.id, commit=False)
        relations = build_relations_for_document(session, document.id, commit=False)
    except Exception as e:
        session.rollback()
        document = session.get(Document, document.id)
        document.intelligence_status = "error"
        document.intelligence_error = str(e)
        session.add(document)
        session.commit()
        return {"success": False, "message": str(e)}

    document.intelligence_status = "ready"
    document.intelligence_error = None
    document.intelligence_processed_at = utc_now()
    session.add(document)
    session.commit()
    session.refresh(document)
    return {
        "success": True,
        "message": "Document intelligence processed.",
        "entities": len(entities),
        "relations": len(relations),
        "obligations": len(obligations),
        "risks": len(risks),
    }


def recompute_all_intelligence(session: Session) -> dict:
    documents = session.exec(select(Document).where(Document.raw_text.is_not(None))).all()
    processed = 0
    errors = 0
    for document in documents:
        result = process_document_intelligence(session, document)
        if result["success"]:
            processed += 1
        else:
            errors += 1
    return {"processed": processed, "errors": errors, "total": len(documents)}
