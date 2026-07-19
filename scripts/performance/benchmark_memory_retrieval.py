#!/usr/bin/env python3
"""Summarize AREQA long-term memory retrieval traces.

This Phase 4A helper reads backend logs containing
``orchestration.long_term_memory_retrieval_summary`` events and produces a
privacy-safe aggregate report. It does not require raw prompts or memory
contents, and it should be run against copied backend logs from a benchmark
window.
"""

from __future__ import annotations

import argparse
import json
import math
import re
import statistics
from pathlib import Path
from typing import Any


SUMMARY_PATTERN = re.compile(
    r"orchestration\.long_term_memory_retrieval_summary .*? summary=(\{.*\})"
)


def percentile(values: list[float], quantile: float) -> float | None:
    """Return an interpolated percentile for non-empty values."""

    if not values:
        return None
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def parse_summaries(log_text: str) -> list[dict[str, Any]]:
    """Extract safe memory retrieval summaries from backend log text."""

    summaries: list[dict[str, Any]] = []
    for match in SUMMARY_PATTERN.finditer(log_text):
        try:
            summaries.append(json.loads(match.group(1)))
        except json.JSONDecodeError:
            continue
    return summaries


def summarize(summaries: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate memory retrieval outcomes and sub-step latencies."""

    elapsed = [float(item.get("elapsed_ms", 0)) for item in summaries]
    outcomes: dict[str, int] = {}
    cache_statuses: dict[str, int] = {}
    step_durations: dict[str, list[float]] = {}

    for item in summaries:
        outcome = str(item.get("outcome") or "unknown")
        cache_status = str(item.get("cache_status") or "unknown")
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
        cache_statuses[cache_status] = cache_statuses.get(cache_status, 0) + 1
        for step in item.get("steps", []):
            name = str(step.get("name") or "unknown")
            step_durations.setdefault(name, []).append(float(step.get("duration_ms", 0)))

    step_summary = {
        name: {
            "samples": len(values),
            "median_ms": round(statistics.median(values), 2),
            "p95_ms": round(percentile(values, 0.95) or 0, 2),
            "max_ms": round(max(values), 2),
        }
        for name, values in sorted(step_durations.items())
    }

    timeout_count = outcomes.get("timeout", 0)
    retrieved_count = outcomes.get("retrieved", 0)
    empty_count = outcomes.get("empty", 0)
    total = len(summaries)
    return {
        "schema_version": 1,
        "samples": total,
        "memory_elapsed_median_ms": round(statistics.median(elapsed), 2) if elapsed else None,
        "memory_elapsed_p95_ms": round(percentile(elapsed, 0.95) or 0, 2) if elapsed else None,
        "timeout_rate": round(timeout_count / total, 4) if total else None,
        "retrieved_rate": round(retrieved_count / total, 4) if total else None,
        "empty_rate": round(empty_count / total, 4) if total else None,
        "outcomes": dict(sorted(outcomes.items())),
        "cache_statuses": dict(sorted(cache_statuses.items())),
        "steps": step_summary,
        "top_steps_by_p95": sorted(
            (
                {"name": name, **metrics}
                for name, metrics in step_summary.items()
            ),
            key=lambda item: item["p95_ms"],
            reverse=True,
        )[:10],
    }


def render_markdown(report: dict[str, Any]) -> str:
    """Render a compact Markdown summary."""

    lines = [
        "# AREQA Memory Retrieval Benchmark",
        "",
        f"Samples: `{report['samples']}`",
        f"Memory elapsed median: `{report['memory_elapsed_median_ms']} ms`",
        f"Memory elapsed p95: `{report['memory_elapsed_p95_ms']} ms`",
        f"Timeout rate: `{report['timeout_rate']}`",
        f"Retrieved rate: `{report['retrieved_rate']}`",
        f"Empty rate: `{report['empty_rate']}`",
        "",
        "| Step | Samples | Median | P95 | Max |",
        "|---|---:|---:|---:|---:|",
    ]
    for step in report["top_steps_by_p95"]:
        lines.append(
            f"| `{step['name']}` | {step['samples']} | {step['median_ms']:.2f} ms "
            f"| {step['p95_ms']:.2f} ms | {step['max_ms']:.2f} ms |"
        )
    lines.append("")
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for log-based memory retrieval aggregation."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-file", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    """Run the log parser and write JSON plus Markdown artifacts."""

    args = parse_args()
    summaries = parse_summaries(args.log_file.read_text(encoding="utf-8", errors="replace"))
    report = summarize(summaries)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    markdown_path = args.output.with_suffix(".md")
    markdown_path.write_text(render_markdown(report), encoding="utf-8")
    print(render_markdown(report))
    print(f"JSON: {args.output}")
    print(f"Markdown: {markdown_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
