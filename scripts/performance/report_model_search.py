"""Compare model tool routing with the routing classifier from backend logs.

During the P6 rollout, model-routed AUTO turns log the model's choice
(``orchestration.model_search_decision called=``) and, off the critical path,
what the classifier would have chosen (``orchestration.model_search_shadow
classifier_search=``). Classifier-routed AUTO turns are the control group.

Prints:
1. Agreement between the model and the classifier on model-routed turns.
2. Time to first answer for model-routed turns (searched / answered directly)
   against classifier-routed turns (searched / not), the rollout's kill metric.

Usage:
    python scripts/performance/report_model_search.py logs/*.log

Reads only ids, decisions and timings; log lines never carry user text.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict, deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))
from report_turn_latency import _SUMMARY, _pairs, percentile  # noqa: E402


@dataclass
class ModelSearchReport:
    # (model_called, classifier_search) -> count
    agreement: dict[tuple[bool, bool], int] = field(default_factory=lambda: defaultdict(int))
    unpaired_decisions: int = 0
    ttfa: dict[str, list[int]] = field(default_factory=lambda: defaultdict(list))


def build_report(lines: Iterable[str]) -> ModelSearchReport:
    """Pair each turn's logs per conversation in log order.

    The shadow is logged when the classifier finishes, which may be after the
    model's decision, so both sides queue per conversation and pair FIFO.
    """
    report = ModelSearchReport()
    shadows: dict[str, deque[bool]] = defaultdict(deque)
    decisions: dict[str, deque[bool]] = defaultdict(deque)
    # Group the next turn trace of each conversation falls into.
    pending: dict[str, str] = {}

    def pair(conversation: str) -> None:
        while shadows[conversation] and decisions[conversation]:
            called = decisions[conversation].popleft()
            report.agreement[(called, shadows[conversation].popleft())] += 1

    for line in lines:
        if "orchestration.search_decision" in line:
            pairs = _pairs(line, "orchestration.search_decision")
            conversation = pairs.get("conversation_id", "")
            if pairs.get("effective_search_mode") != "auto":
                pending.pop(conversation, None)
            elif pairs.get("reason") == "MODEL_TOOL_ROUTING":
                pending[conversation] = "model"
            else:
                pending[conversation] = "classifier_search" if pairs.get("should_search") == "True" else "classifier_direct"
        elif "orchestration.model_search_decision" in line:
            pairs = _pairs(line, "orchestration.model_search_decision")
            conversation = pairs.get("conversation_id", "")
            called = pairs.get("called") == "True"
            decisions[conversation].append(called)
            if pending.get(conversation) == "model":
                pending[conversation] = "model_search" if called else "model_direct"
            pair(conversation)
        elif "orchestration.model_search_shadow " in line:
            pairs = _pairs(line, "orchestration.model_search_shadow")
            conversation = pairs.get("conversation_id", "")
            shadows[conversation].append(pairs.get("classifier_search") == "True")
            pair(conversation)
        elif match := _SUMMARY.search(line):
            try:
                summary = json.loads(match.group(1))
            except ValueError:
                continue
            group = pending.pop(str(summary.get("conversation_id", "")), None)
            ttfa = summary.get("time_to_first_answer_ms")
            if group and group != "model" and isinstance(ttfa, int):
                report.ttfa[group].append(ttfa)
    report.unpaired_decisions = sum(len(queue) for queue in decisions.values())
    return report


def render(report: ModelSearchReport) -> str:
    both = report.agreement[(True, True)]
    neither = report.agreement[(False, False)]
    model_only = report.agreement[(True, False)]
    classifier_only = report.agreement[(False, True)]
    paired = both + neither + model_only + classifier_only
    agree = f"{(both + neither) / paired:.1%}" if paired else "n/a"
    classifier_total = both + classifier_only
    recall = f"{both / classifier_total:.1%}" if classifier_total else "n/a"
    lines = [
        "## 1. Model vs classifier (model-routed turns)",
        f"paired_turns={paired} agreement={agree} unpaired_model_decisions={report.unpaired_decisions}",
        f"both_search={both} neither={neither} model_only={model_only} classifier_only={classifier_only}",
        f"model_search_rate={(both + model_only) / paired:.1%}" if paired else "model_search_rate=n/a",
        f"classifier_search_rate={classifier_total / paired:.1%}" if paired else "classifier_search_rate=n/a",
        f"recall_vs_classifier={recall}  (proxy only: logs have no ground truth; the spec's kill line "
        "uses recall on a labeled query set)",
        "",
        "## 2. Time to first answer (ms)",
    ]
    for group in ("model_search", "classifier_search", "model_direct", "classifier_direct"):
        values = report.ttfa.get(group, [])
        lines.append(f"{group:<18} n={len(values)} p50={percentile(values, 0.5)} p95={percentile(values, 0.95)}")
    lines.append("spec kill line: model_search p95 more than 2000 ms above classifier_search p95")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("logs", nargs="+", type=Path)
    args = parser.parse_args(argv)

    def lines() -> Iterable[str]:
        for path in args.logs:
            with path.open(encoding="utf-8", errors="replace") as handle:
                yield from handle

    print(render(build_report(lines())))
    return 0


if __name__ == "__main__":
    sys.exit(main())
