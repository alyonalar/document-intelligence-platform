import json
from pathlib import Path

from app.services.intelligence_evaluation import evaluate_intelligence_dataset

if __name__ == "__main__":
    dataset = Path("tests/fixtures/intelligence_eval.json")
    print(json.dumps(evaluate_intelligence_dataset(dataset), indent=2))
