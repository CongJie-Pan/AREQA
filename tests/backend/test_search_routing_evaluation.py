import json
from pathlib import Path

from scripts.performance.evaluate_search_routing import evaluate


def test_search_routing_dataset_meets_shadow_gate():
    dataset = Path("tests/fixtures/search_routing_cases.json")
    metrics = evaluate(json.loads(dataset.read_text(encoding="utf-8")))

    assert metrics["cases"] >= 10
    assert metrics["precision"] >= 0.9
    assert metrics["recall"] >= 0.9
    assert metrics["privacy_violations"] == 0
