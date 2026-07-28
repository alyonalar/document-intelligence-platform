import json
from pathlib import Path

from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine, select

from app.db.models import Document, DocumentEntity, DocumentObligation, DocumentRisk
from app.services.entity_extraction_service import normalize_entity_value
from app.services.intelligence_pipeline import process_document_intelligence


def _prf(expected: set[tuple], predicted: set[tuple]) -> dict[str, float | int]:
    true_positive = len(expected & predicted)
    precision = true_positive / len(predicted) if predicted else float(not expected)
    recall = true_positive / len(expected) if expected else float(not predicted)
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "expected": len(expected),
        "predicted": len(predicted),
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3),
    }


def evaluate_intelligence_dataset(dataset_path: Path) -> dict:
    cases = json.loads(dataset_path.read_text(encoding="utf-8"))
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)

    expected_entities: set[tuple] = set()
    predicted_entities: set[tuple] = set()
    expected_risks: set[tuple] = set()
    predicted_risks: set[tuple] = set()
    obligation_matches = 0

    with Session(engine) as session:
        for case in cases:
            document = Document(
                filename=f"{case['id']}.txt",
                stored_path=f"evaluation/{case['id']}.txt",
                file_type="txt",
                file_size=len(case["text"].encode("utf-8")),
                raw_text=case["text"],
            )
            session.add(document)
            session.commit()
            session.refresh(document)
            result = process_document_intelligence(session, document)
            if not result["success"]:
                raise RuntimeError(f"Evaluation case {case['id']} failed: {result['message']}")

            expected_entities.update(
                (
                    case["id"],
                    entity_type,
                    normalize_entity_value(entity_type, value),
                )
                for entity_type, value in case["entities"]
            )
            predicted_entities.update(
                (case["id"], entity.entity_type, entity.normalized_value or "")
                for entity in session.exec(
                    select(DocumentEntity).where(DocumentEntity.document_id == document.id)
                ).all()
            )
            expected_risks.update((case["id"], value) for value in case["risks"])
            predicted_risks.update(
                (case["id"], risk.risk_type)
                for risk in session.exec(
                    select(DocumentRisk).where(DocumentRisk.document_id == document.id)
                ).all()
            )
            has_obligation = bool(
                session.exec(
                    select(DocumentObligation).where(DocumentObligation.document_id == document.id)
                ).first()
            )
            obligation_matches += has_obligation == case["has_obligation"]

    return {
        "cases": len(cases),
        "entities": _prf(expected_entities, predicted_entities),
        "risks": _prf(expected_risks, predicted_risks),
        "obligation_detection_accuracy": round(obligation_matches / len(cases), 3),
    }
