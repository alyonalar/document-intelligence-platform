from datetime import timedelta
from uuid import uuid4

from sqlmodel import Session, select

from app.db.engine import engine
from app.db.models import Document, DocumentEntity, EntityAlias, utc_now
from app.services import intelligence_pipeline
from app.services.entity_extraction_service import extract_entities
from app.services.obligation_service import (
    extract_obligations,
    mark_obligation_done,
    update_obligation_statuses,
)
from app.services.relationship_graph_service import (
    build_relations_for_document,
    find_related_documents,
    list_relations_for_document,
)
from app.services.risk_detection_service import detect_risks


def add_document(session: Session, text: str, filename: str | None = None) -> Document:
    document = Document(
        filename=filename or f"intel-{uuid4().hex}.txt",
        stored_path="data/test_uploads/intel.txt",
        file_type="txt",
        file_size=len(text),
        title="Intelligence Test",
        raw_text=text,
        word_count=len(text.split()),
        estimated_reading_time_min=1,
        summary_short="Test summary",
    )
    session.add(document)
    session.commit()
    session.refresh(document)
    return document


def test_entity_extraction_dates_amount_organization_and_contract_number():
    with Session(engine) as session:
        document = add_document(
            session, "Contract no. C-100 with TOO Romashka on 2026-01-10 for 150000 KZT."
        )
        entities = extract_entities(session, document.id)

    assert any(item.entity_type == "date" and item.value == "2026-01-10" for item in entities)
    assert any(item.entity_type == "amount" for item in entities)
    assert any(item.entity_type == "organization" and "Romashka" in item.value for item in entities)
    assert any(item.entity_type == "contract_number" and item.value == "C-100" for item in entities)


def test_entity_extraction_extracts_dates_and_amounts():
    with Session(engine) as session:
        document = add_document(session, "Payment of USD 2,500.00 is due on 2026-03-15.")
        entities = extract_entities(session, document.id)

    assert any(item.entity_type == "date" and item.value == "2026-03-15" for item in entities)
    assert any(item.entity_type == "amount" and "USD" in item.value for item in entities)


def test_entity_extraction_does_not_extract_dates_as_phones():
    with Session(engine) as session:
        document = add_document(
            session,
            "Internal email dated 15.08.2026. Follow up by 01.09.2026 and 10.09.2026. 2 next item.",
        )
        entities = extract_entities(session, document.id)

    assert any(item.entity_type == "date" and item.value == "15.08.2026" for item in entities)
    assert not [item.value for item in entities if item.entity_type == "phone"]


def test_entity_extraction_extracts_organizations():
    with Session(engine) as session:
        document = add_document(session, "The agreement is between TOO Romashka and Atlas LLP.")
        entities = extract_entities(session, document.id)

    organizations = [item.value for item in entities if item.entity_type == "organization"]
    assert any("TOO Romashka" in value for value in organizations)
    assert any("Atlas LLP" in value for value in organizations)


def test_entity_extraction_extracts_contract_invoice_and_act_numbers():
    with Session(engine) as session:
        document = add_document(
            session,
            "Contract no. C-777 references invoice # INV-888 and act № ACT-999.",
        )
        entities = extract_entities(session, document.id)

    assert any(item.entity_type == "contract_number" and item.value == "C-777" for item in entities)
    assert any(
        item.entity_type == "invoice_number" and item.value == "INV-888" for item in entities
    )
    assert any(item.entity_type == "act_number" and item.value == "ACT-999" for item in entities)


def test_act_pattern_does_not_match_contract_or_contact_substrings():
    with Session(engine) as session:
        document = add_document(
            session,
            "Contract no. C-1. Contact legal@example.com.",
        )
        entities = extract_entities(session, document.id)

    assert not [item for item in entities if item.entity_type == "act_number"]


def test_explicit_entity_alias_is_resolved_to_canonical_value():
    with Session(engine) as session:
        session.add(
            EntityAlias(
                entity_type="organization",
                alias_value="atlas llp",
                canonical_value="atlas group",
            )
        )
        session.commit()
        document = add_document(session, "The agreement is with Atlas LLP.")
        entities = extract_entities(session, document.id)

    organization = next(item for item in entities if item.entity_type == "organization")
    assert organization.normalized_value == "atlas group"


def test_obligation_extraction_with_fixed_due_date():
    with Session(engine) as session:
        due_date = (utc_now() + timedelta(days=30)).date().isoformat()
        document = add_document(session, f"Atlas LLP must pay 150000 KZT no later than {due_date}.")
        obligations = extract_obligations(session, document.id)

    assert len(obligations) == 1
    assert obligations[0].due_date_text == due_date
    assert obligations[0].status == "open"


def test_obligation_extraction_with_relative_within_days_due_date():
    with Session(engine) as session:
        document = add_document(session, "Customer should submit objections within 5 days.")
        obligations = extract_obligations(session, document.id)

    assert len(obligations) == 1
    assert obligations[0].due_date_text == "within 5 days"
    assert obligations[0].due_date is not None
    assert obligations[0].status == "open"


def test_overdue_obligation_status():
    with Session(engine) as session:
        past = (utc_now() - timedelta(days=3)).date().isoformat()
        document = add_document(session, f"Atlas LLP must pay no later than {past}.")
        obligations = extract_obligations(session, document.id)
        update_obligation_statuses(session)
        status = obligations[0].status

    assert status == "overdue"


def test_obligations_extracts_due_date_overdue_done_and_no_due_date():
    with Session(engine) as session:
        past = (utc_now() - timedelta(days=10)).date().isoformat()
        document = add_document(
            session,
            f"Atlas LLP must pay 150000 KZT no later than {past}. Team should provide report.",
        )
        obligations = extract_obligations(session, document.id)
        update_obligation_statuses(session)
        statuses = [item.status for item in obligations]
        due_dates = [item.due_date_text for item in obligations]
        done = mark_obligation_done(session, obligations[0].id)
        done_status = done.status

    assert past in due_dates
    assert "overdue" in statuses
    assert "no_due_date" in statuses
    assert done_status == "done"


def test_risks_detects_penalty_auto_renewal_and_severity():
    with Session(engine) as session:
        document = add_document(
            session, "The contract has penalty, liability and automatic renewal clauses."
        )
        risks = detect_risks(session, document.id)

    assert any(item.risk_type == "penalty" and item.severity == "high" for item in risks)
    assert any(item.risk_type == "auto_renewal" and item.severity == "high" for item in risks)


def test_risk_detection_for_penalty():
    with Session(engine) as session:
        document = add_document(session, "A penalty of 10% applies for late payment.")
        risks = detect_risks(session, document.id)

    assert any(item.risk_type == "penalty" and item.severity == "high" for item in risks)


def test_risk_detection_for_auto_renewal():
    with Session(engine) as session:
        document = add_document(session, "The agreement includes automatic renewal for one year.")
        risks = detect_risks(session, document.id)

    assert any(item.risk_type == "auto_renewal" and item.severity == "high" for item in risks)


def test_relations_link_documents_by_organization_and_contract_number():
    with Session(engine) as session:
        contract = add_document(
            session, "Contract no. C-200 with TOO Romashka.", "contract-c200.txt"
        )
        invoice = add_document(
            session,
            "Invoice # I-1 references contract no. C-200 for TOO Romashka.",
            "invoice-c200.txt",
        )
        extract_entities(session, contract.id)
        extract_entities(session, invoice.id)
        build_relations_for_document(session, invoice.id)
        related = find_related_documents(session, invoice.id)

    assert any(document.id == contract.id for document in related)


def test_relation_generation_by_shared_contract_number():
    with Session(engine) as session:
        contract = add_document(
            session, "Contract no. REL-500 with Atlas LLP.", "contract-rel-500.txt"
        )
        invoice = add_document(
            session, "Invoice # I-500 references contract no. REL-500.", "invoice-rel-500.txt"
        )
        extract_entities(session, contract.id)
        extract_entities(session, invoice.id)
        build_relations_for_document(session, invoice.id)
        relations = list_relations_for_document(session, invoice.id)
        contract_id = contract.id

    assert any(
        item.target_document_id == contract_id and item.relation_type == "references_contract"
        for item in relations
    )


def test_intelligence_recompute_rolls_back_partial_artifacts(monkeypatch):
    with Session(engine) as session:
        document = add_document(session, "Contact new@example.com before 2026-09-05.")
        session.add(
            DocumentEntity(
                document_id=document.id,
                entity_type="email",
                value="old@example.com",
                normalized_value="old@example.com",
            )
        )
        session.commit()

        def fail_risk_detection(*_args, **_kwargs):
            raise RuntimeError("simulated rule failure")

        monkeypatch.setattr(intelligence_pipeline, "detect_risks", fail_risk_detection)
        result = intelligence_pipeline.process_document_intelligence(session, document)
        entities = session.exec(
            select(DocumentEntity).where(DocumentEntity.document_id == document.id)
        ).all()
        session.refresh(document)

    assert result["success"] is False
    assert document.intelligence_status == "error"
    assert [item.value for item in entities] == ["old@example.com"]
