from sqlalchemy import delete
from sqlmodel import Session, select

from app.db.models import Document, DocumentRisk
from app.services.intelligence_utils import split_sentences

RISK_PATTERNS = [
    ("penalty", "high", ["штраф", "неустойка", "пеня", "penalty"]),
    ("fine", "high", ["fine"]),
    ("auto_renewal", "high", ["автоматическая пролонгация", "auto-renewal", "automatic renewal"]),
    ("termination", "high", ["расторжение", "односторонний отказ", "termination"]),
    ("payment_delay", "medium", ["просрочк", "late payment"]),
    ("confidentiality", "medium", ["конфиденциальность", "confidentiality"]),
    ("liability", "medium", ["ответственность", "liability"]),
    ("vague_terms", "medium", ["reasonable efforts", "best efforts", "по согласованию сторон"]),
    ("custom", "low", ["breach"]),
]


def _rule_score(keyword: str, severity: str) -> float:
    score = {"high": 0.72, "medium": 0.64, "low": 0.58}[severity]
    if " " in keyword or "-" in keyword:
        score += 0.1
    return min(score, 0.9)


def detect_risks(
    session: Session,
    document_id: int,
    *,
    commit: bool = True,
) -> list[DocumentRisk]:
    document = session.get(Document, document_id)
    if not document:
        raise ValueError("Document not found")
    session.exec(delete(DocumentRisk).where(DocumentRisk.document_id == document_id))
    risks = []
    seen: set[tuple[str, str]] = set()
    for index, sentence in enumerate(split_sentences(document.raw_text or ""), start=1):
        lower = sentence.lower()
        for risk_type, severity, keywords in RISK_PATTERNS:
            matched_keyword = next(
                (keyword for keyword in keywords if keyword.lower() in lower),
                None,
            )
            if matched_keyword is None:
                continue
            key = (risk_type, sentence)
            if key in seen:
                continue
            seen.add(key)
            risk = DocumentRisk(
                document_id=document_id,
                risk_type=risk_type,
                title=f"{severity.title()} {risk_type.replace('_', ' ')} risk",
                description=f"Potential {risk_type.replace('_', ' ')} clause detected.",
                severity=severity,
                source_text=sentence,
                chunk_index=index,
                confidence=_rule_score(matched_keyword, severity),
            )
            session.add(risk)
            risks.append(risk)
    if commit:
        session.commit()
    else:
        session.flush()
    for risk in risks:
        session.refresh(risk)
    return risks


def get_risks_by_document(session: Session, document_id: int) -> list[DocumentRisk]:
    return session.exec(
        select(DocumentRisk)
        .where(DocumentRisk.document_id == document_id)
        .order_by(DocumentRisk.severity.desc())
    ).all()


def list_risks(
    session: Session, severity: str = "", risk_type: str = "", document_id: int | None = None
) -> list[DocumentRisk]:
    statement = select(DocumentRisk)
    if severity:
        statement = statement.where(DocumentRisk.severity == severity)
    if risk_type:
        statement = statement.where(DocumentRisk.risk_type == risk_type)
    if document_id is not None:
        statement = statement.where(DocumentRisk.document_id == document_id)
    return session.exec(statement.order_by(DocumentRisk.created_at.desc())).all()


def get_risks_summary(session: Session) -> dict:
    risks = list_risks(session)
    return {
        "total": len(risks),
        "high": sum(1 for risk in risks if risk.severity == "high"),
        "medium": sum(1 for risk in risks if risk.severity == "medium"),
        "low": sum(1 for risk in risks if risk.severity == "low"),
        "by_type": {
            risk_type: sum(1 for risk in risks if risk.risk_type == risk_type)
            for risk_type in sorted({risk.risk_type for risk in risks})
        },
    }
