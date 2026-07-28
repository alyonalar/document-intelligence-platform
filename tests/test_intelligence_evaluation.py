from pathlib import Path

from app.services.intelligence_evaluation import evaluate_intelligence_dataset


def test_rule_based_intelligence_meets_documented_baseline():
    report = evaluate_intelligence_dataset(Path("tests/fixtures/intelligence_eval.json"))

    assert report["cases"] >= 8
    assert report["entities"]["precision"] >= 0.9
    assert report["entities"]["recall"] >= 0.9
    assert report["risks"]["precision"] >= 0.9
    assert report["risks"]["recall"] >= 0.9
    assert report["obligation_detection_accuracy"] >= 0.9
