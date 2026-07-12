#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from core.run_context import SearchMode
from policies.search_policy import SearchPolicy


def evaluate(cases: list[dict]) -> dict[str, float | int]:
    policy = SearchPolicy()
    true_positive = false_positive = false_negative = true_negative = 0
    privacy_violations = 0

    for case in cases:
        mode = SearchMode(case["mode"])
        actual = policy.evaluate(case["query"], mode).should_search
        expected = bool(case["should_search"])
        true_positive += int(actual and expected)
        false_positive += int(actual and not expected)
        false_negative += int(not actual and expected)
        true_negative += int(not actual and not expected)
        privacy_violations += int(mode == SearchMode.NEVER and actual)

    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 1.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 1.0
    return {
        "cases": len(cases),
        "precision": precision,
        "recall": recall,
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "true_negative": true_negative,
        "privacy_violations": privacy_violations,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Evaluate Tutor shadow search routing")
    parser.add_argument(
        "--dataset",
        type=Path,
        default=ROOT / "tests/fixtures/search_routing_cases.json",
    )
    parser.add_argument("--min-precision", type=float, default=0.9)
    parser.add_argument("--min-recall", type=float, default=0.9)
    args = parser.parse_args()

    metrics = evaluate(json.loads(args.dataset.read_text(encoding="utf-8")))
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    passed = (
        metrics["precision"] >= args.min_precision
        and metrics["recall"] >= args.min_recall
        and metrics["privacy_violations"] == 0
    )
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
