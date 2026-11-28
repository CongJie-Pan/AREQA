"""Baseline latency and cache report from AREQA backend logs.

Reads the structured key=value log lines the backend already emits and prints
the three baselines the opencode-improvements spec measures against:

1. Turns that needed history compaction, and their time to first answer.
2. Provider prefix-cache hit share, split by whether the turn had attachments.
3. Search-routing latency and how often routing chose to search.

Usage:
    python scripts/performance/report_turn_latency.py temp/logs.md [more.log ...]

Only identifiers, counts and timings are read; log lines never carry user text.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

_PAIR = re.compile(r"(\w+)=(\S+)")
_SUMMARY = re.compile(r"orchestration\.turn_trace_summary .*?summary=(\{.*\})\s*$")


def _pairs(line: str, event: str) -> dict[str, str]:
    return dict(_PAIR.findall(line.split(event, 1)[1]))


def _int(value: str | None) -> int:
    try:
        return int(value or 0)
    except ValueError:
        return 0


def percentile(values: list[int], share: float) -> int | None:
    """Nearest-rank percentile; None for an empty list."""
    if not values:
        return None
    ordered = sorted(values)
    rank = max(1, round(share * len(ordered) + 0.5 - 1e-9))
    return ordered[min(rank, len(ordered)) - 1]


@dataclass
class Report:
    ttfa_compacted: list[int] = field(default_factory=list)
    ttfa_plain: list[int] = field(default_factory=list)
    cache: dict[bool, list[int]] = field(default_factory=lambda: {True: [0, 0], False: [0, 0]})
    routing_ms: list[int] = field(default_factory=list)
    search_decisions: list[bool] = field(default_factory=list)


def build_report(lines: Iterable[str]) -> Report:
    """Fold log lines into a report. Turns are matched per conversation in log order."""
    report = Report()
    pending_compaction: dict[str, bool] = defaultdict(bool)
    has_attachments: dict[str, bool] = defaultdict(bool)
    for line in lines:
        if "history.budget_evaluated" in line:
            pairs = _pairs(line, "history.budget_evaluated")
            if pairs.get("compaction_required") == "True":
                pending_compaction[pairs.get("conversation_id", "")] = True
        elif "orchestration.stream_started" in line:
            pairs = _pairs(line, "orchestration.stream_started")
            has_attachments[pairs.get("conversation_id", "")] = pairs.get("attachment_parser") == "True"
        elif "orchestration.provider_finish" in line:
            pairs = _pairs(line, "orchestration.provider_finish")
            bucket = report.cache[has_attachments[pairs.get("conversation_id", "")]]
            bucket[0] += _int(pairs.get("cached_tokens"))
            bucket[1] += _int(pairs.get("prompt_tokens"))
        elif "orchestration.search_decision" in line:
            pairs = _pairs(line, "orchestration.search_decision")
            if pairs.get("effective_search_mode") == "auto":
                report.search_decisions.append(pairs.get("should_search") == "True")
        elif match := _SUMMARY.search(line):
            try:
                summary = json.loads(match.group(1))
            except ValueError:
                continue
            conversation = str(summary.get("conversation_id", ""))
            ttfa = summary.get("time_to_first_answer_ms")
            if isinstance(ttfa, int):
                target = report.ttfa_compacted if pending_compaction[conversation] else report.ttfa_plain
                target.append(ttfa)
            pending_compaction[conversation] = False
            routing = summary.get("phase_durations_ms", {}).get("search_routing")
            if isinstance(routing, int) and routing > 0:
                report.routing_ms.append(routing)
    return report


def render(report: Report) -> str:
    def stats(values: list[int]) -> str:
        return f"n={len(values)} p50={percentile(values, 0.5)} p95={percentile(values, 0.95)}"

    total_turns = len(report.ttfa_compacted) + len(report.ttfa_plain)
    share = len(report.ttfa_compacted) / total_turns if total_turns else 0.0
    lines = [
        "## 1. History compaction",
        f"turns={total_turns} compaction_turns={len(report.ttfa_compacted)} share={share:.1%}",
        f"time_to_first_answer_ms compaction: {stats(report.ttfa_compacted)}",
        f"time_to_first_answer_ms other:      {stats(report.ttfa_plain)}",
        "",
        "## 2. Provider prefix cache",
    ]
    for label, key in (("with attachments", True), ("without attachments", False)):
        cached, prompt = report.cache[key]
        ratio = f"{cached / prompt:.1%}" if prompt else "n/a"
        lines.append(f"{label}: cached_tokens={cached} prompt_tokens={prompt} hit={ratio}")
    searched = sum(report.search_decisions)
    decided = len(report.search_decisions)
    lines += [
        "",
        "## 3. Search routing (AUTO mode)",
        f"routing_ms: {stats(report.routing_ms)}",
        f"should_search={searched}/{decided}" + (f" ({searched / decided:.1%})" if decided else ""),
    ]
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
