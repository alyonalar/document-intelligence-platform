import re
from collections import OrderedDict

from pydantic import BaseModel, Field
from sqlalchemy import delete
from sqlmodel import Session, select

from app.db.models import Document, DocumentEntity, EntityAlias


class ExtractedEntity(BaseModel):
    entity_type: str
    value: str
    source_text: str = ""
    confidence: float = Field(default=0.7, ge=0, le=1)


DATE_PATTERNS = [
    r"\b\d{4}-\d{2}-\d{2}\b",
    r"\b\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\b",
    r"\b\d{1,2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4}\b",
]
AMOUNT_PATTERN = r"(?:(?:USD|EUR|KZT|RUB|₸|\$|€)\s*)?\b\d+(?:[\s,]\d{3})*(?:[.,]\d{2})?\b\s*(?:USD|EUR|KZT|RUB|тенге|руб(?:\.|лей)?|₸|\$|€)?"
EMAIL_PATTERN = r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b"
PHONE_PATTERN = r"(?<!\w)(?:\+?\d[\d\s().-]{7,}\d)(?!\w)"
ORG_PATTERN = (
    r"\b(?:ТОО|TOO|ООО|ИП|АО)\s+[\"']?[A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9& .-]{1,60}"
    r"|\b[\"']?[A-ZА-Я][A-Za-zА-Яа-я0-9&.-]*(?:\s+[A-ZА-Я][A-Za-zА-Яа-я0-9&.-]*){0,3}"
    r"\s+(?:LLP|Inc\.?|Ltd\.?|Company)\b"
)
NUMBER_PATTERNS = [
    (
        "contract_number",
        r"\b(?:договор|contract|agreement)\b\s*(?:№|#|no\.?|number)?\s*([A-Za-zА-Яа-я0-9/_-]{2,})",
    ),
    (
        "invoice_number",
        r"\b(?:счет|сч[её]т|invoice)\b\s*(?:№|#|no\.?|number)?\s*([A-Za-zА-Яа-я0-9/_-]{2,})",
    ),
    ("act_number", r"\b(?:акт|act)\b\s*(?:№|#|no\.?|number)?\s*([A-Za-zА-Яа-я0-9/_-]{2,})"),
    (
        "document_number",
        r"\b(?:документ|document)\b\s*(?:№|#|no\.?|number)?\s*([A-Za-zА-Яа-я0-9/_-]{2,})",
    ),
]


def normalize_entity_value(entity_type: str, value: str) -> str:
    normalized = " ".join(value.strip().strip("\"'.,;:()[]").split())
    if entity_type in {
        "email",
        "organization",
        "person",
        "document_number",
        "contract_number",
        "invoice_number",
        "act_number",
    }:
        return normalized.lower()
    if entity_type == "phone":
        return re.sub(r"\D+", "", normalized)
    if entity_type == "amount":
        return re.sub(r"\s+", "", normalized).replace(",", ".").lower()
    return normalized


def _context(text: str, start: int, end: int, radius: int = 90) -> str:
    return " ".join(text[max(0, start - radius) : min(len(text), end + radius)].split())


def _add_entity(
    items: OrderedDict, entity_type: str, value: str, source_text: str, confidence: float
) -> None:
    value = " ".join(value.strip().split())
    if not value or len(value) < 2:
        return
    key = (entity_type, normalize_entity_value(entity_type, value))
    if key not in items:
        items[key] = ExtractedEntity(
            entity_type=entity_type,
            value=value,
            source_text=source_text or value,
            confidence=confidence,
        )


def looks_like_date(value: str) -> bool:
    cleaned = value.strip()
    if any(re.fullmatch(pattern, cleaned, flags=re.IGNORECASE) for pattern in DATE_PATTERNS):
        return True
    # Phone regex can over-capture a date plus a following sentence/list number,
    # for example "05.09.2026. 2". Treat that as a date false positive too.
    return bool(
        re.fullmatch(
            r"\d{1,2}[./-]\d{1,2}[./-]\d{2,4}[.\s-]*\d*",
            cleaned,
            flags=re.IGNORECASE,
        )
    )


def is_phone_date_false_positive(entity_type: str, value: str) -> bool:
    return entity_type == "phone" and looks_like_date(value)


def _extract_rule_based(text: str) -> list[ExtractedEntity]:
    items: OrderedDict[tuple[str, str], ExtractedEntity] = OrderedDict()

    for pattern in DATE_PATTERNS:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            _add_entity(
                items, "date", match.group(0), _context(text, match.start(), match.end()), 0.85
            )

    for entity_type, pattern in [
        ("amount", AMOUNT_PATTERN),
        ("email", EMAIL_PATTERN),
        ("phone", PHONE_PATTERN),
        ("organization", ORG_PATTERN),
    ]:
        flags = 0 if entity_type == "organization" else re.IGNORECASE
        for match in re.finditer(pattern, text, flags=flags):
            value = match.group(0)
            if entity_type == "amount" and not re.search(
                r"USD|EUR|KZT|RUB|тенге|руб|₸|\$|€", value, re.IGNORECASE
            ):
                continue
            if entity_type == "phone" and looks_like_date(value):
                continue
            _add_entity(items, entity_type, value, _context(text, match.start(), match.end()), 0.75)

    for entity_type, pattern in NUMBER_PATTERNS:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            value = match.group(1)
            _add_entity(items, entity_type, value, _context(text, match.start(), match.end()), 0.82)

    return list(items.values())


def resolve_entity_alias(
    session: Session,
    entity_type: str,
    normalized_value: str,
) -> str:
    alias = session.exec(
        select(EntityAlias).where(
            EntityAlias.entity_type == entity_type,
            EntityAlias.alias_value == normalized_value,
        )
    ).first()
    if alias:
        return normalize_entity_value(entity_type, alias.canonical_value)
    return normalized_value


def save_entities(
    session: Session,
    document_id: int,
    entities: list[ExtractedEntity],
    *,
    commit: bool = True,
) -> list[DocumentEntity]:
    session.exec(delete(DocumentEntity).where(DocumentEntity.document_id == document_id))
    saved = []
    seen: set[tuple[str, str]] = set()
    for entity in entities:
        if is_phone_date_false_positive(entity.entity_type, entity.value):
            continue
        normalized = normalize_entity_value(entity.entity_type, entity.value)
        normalized = resolve_entity_alias(session, entity.entity_type, normalized)
        key = (entity.entity_type, normalized)
        if key in seen:
            continue
        seen.add(key)
        saved_entity = DocumentEntity(
            document_id=document_id,
            entity_type=entity.entity_type,
            value=entity.value,
            normalized_value=normalized,
            source_text=entity.source_text,
            confidence=entity.confidence,
        )
        session.add(saved_entity)
        saved.append(saved_entity)
    if commit:
        session.commit()
    else:
        session.flush()
    for entity in saved:
        session.refresh(entity)
    return saved


def extract_entities(
    session: Session,
    document_id: int,
    *,
    commit: bool = True,
) -> list[DocumentEntity]:
    document = session.get(Document, document_id)
    if not document:
        raise ValueError("Document not found")
    text = document.raw_text or ""
    entities = _extract_rule_based(text)
    return save_entities(session, document_id, entities, commit=commit)


def get_entities_by_document(session: Session, document_id: int) -> list[DocumentEntity]:
    entities = session.exec(
        select(DocumentEntity)
        .where(DocumentEntity.document_id == document_id)
        .order_by(DocumentEntity.entity_type, DocumentEntity.value)
    ).all()
    return [
        entity
        for entity in entities
        if not is_phone_date_false_positive(entity.entity_type, entity.value)
    ]
