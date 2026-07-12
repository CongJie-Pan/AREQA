#!/usr/bin/env python3
"""Benchmark AREQA chat latency without using production data.

Mock mode is a controlled experiment for validating the expected impact of
removing blocking preflight stages. Live mode measures the externally visible
SSE milestones of an existing backend and never runs from pytest implicitly.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import statistics
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, AsyncIterator

import httpx
from dotenv import load_dotenv


VARIANTS = ("baseline", "no_policy_wait", "no_cold_memory", "optimized")
DEFAULT_PROMPTS = (
    "請簡單解釋什麼是成長型思維。",
    "你還記得我之前提過的學習偏好嗎？",
    "心理壓力通常會如何影響專注力？",
)


@dataclass(frozen=True)
class RunMetrics:
    mode: str
    variant: str
    prompt_kind: str
    first_event_ms: float
    first_visible_status_ms: float | None
    main_model_start_ms: float | None
    first_content_ms: float
    completed_ms: float
    completion_calls: int
    embedding_calls: int
    memory_queries: int
    event_counts: dict[str, int]


def percentile(values: list[float], quantile: float) -> float:
    """Return a linearly interpolated percentile without a NumPy dependency."""
    if not values:
        raise ValueError("percentile requires at least one value")
    ordered = sorted(values)
    position = (len(ordered) - 1) * quantile
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    fraction = position - lower
    return ordered[lower] + (ordered[upper] - ordered[lower]) * fraction


def summarize(runs: list[RunMetrics]) -> dict[str, Any]:
    grouped: dict[str, list[RunMetrics]] = {}
    for run in runs:
        grouped.setdefault(run.variant, []).append(run)

    summary: dict[str, Any] = {}
    for variant, samples in grouped.items():
        first_content = [sample.first_content_ms for sample in samples]
        completed = [sample.completed_ms for sample in samples]
        visible = [
            sample.first_visible_status_ms
            for sample in samples
            if sample.first_visible_status_ms is not None
        ]
        summary[variant] = {
            "runs": len(samples),
            "first_content_median_ms": round(statistics.median(first_content), 2),
            "first_content_p95_ms": round(percentile(first_content, 0.95), 2),
            "completed_median_ms": round(statistics.median(completed), 2),
            "completed_p95_ms": round(percentile(completed, 0.95), 2),
            "first_visible_status_median_ms": (
                round(statistics.median(visible), 2) if visible else None
            ),
            "avg_completion_calls": round(
                statistics.mean(sample.completion_calls for sample in samples), 2
            ),
            "avg_embedding_calls": round(
                statistics.mean(sample.embedding_calls for sample in samples), 2
            ),
            "avg_memory_queries": round(
                statistics.mean(sample.memory_queries for sample in samples), 2
            ),
        }

    baseline = summary.get("baseline")
    if baseline:
        baseline_ttft = baseline["first_content_median_ms"]
        for variant, metrics in summary.items():
            if variant == "baseline" or baseline_ttft <= 0:
                metrics["ttft_improvement_percent"] = 0.0
                continue
            metrics["ttft_improvement_percent"] = round(
                (baseline_ttft - metrics["first_content_median_ms"])
                / baseline_ttft
                * 100,
                2,
            )
    return summary


async def run_mock_once(variant: str, prompt_kind: str) -> RunMetrics:
    """Run one deterministic critical-path experiment with controlled delays."""
    started = time.perf_counter()
    await asyncio.sleep(0.001)
    first_event_ms = _elapsed_ms(started)
    first_visible_status_ms = _elapsed_ms(started) if variant == "optimized" else None

    # These controlled delays model the observed ordering, not production speed.
    await asyncio.sleep(0.004)  # memory gate and hot-memory snapshot
    completion_calls = 1  # main answer
    embedding_calls = 0
    memory_queries = 0

    if variant not in {"no_policy_wait", "optimized"}:
        completion_calls += 1
        await asyncio.sleep(0.060)

    if variant not in {"no_cold_memory", "optimized"}:
        completion_calls += 1  # ZPD query rewrite
        embedding_calls += 1
        memory_queries += 2  # cold + GUM memory
        await asyncio.sleep(0.090)

    main_model_start_ms = _elapsed_ms(started)
    await asyncio.sleep(0.020)
    first_content_ms = _elapsed_ms(started)
    await asyncio.sleep(0.025)
    completed_ms = _elapsed_ms(started)

    return RunMetrics(
        mode="mocked",
        variant=variant,
        prompt_kind=prompt_kind,
        first_event_ms=first_event_ms,
        first_visible_status_ms=first_visible_status_ms,
        main_model_start_ms=main_model_start_ms,
        first_content_ms=first_content_ms,
        completed_ms=completed_ms,
        completion_calls=completion_calls,
        embedding_calls=embedding_calls,
        memory_queries=memory_queries,
        event_counts={
            "metadata": 1,
            "status": int(first_visible_status_ms is not None),
            "action": int(first_visible_status_ms is not None),
            "message": 1,
            "done": 1,
        },
    )


def _elapsed_ms(started: float) -> float:
    return (time.perf_counter() - started) * 1000


async def iter_sse_events(response: httpx.Response) -> AsyncIterator[tuple[str, str]]:
    buffer = ""
    async for chunk in response.aiter_text():
        buffer += chunk.replace("\r\n", "\n")
        blocks = buffer.split("\n\n")
        buffer = blocks.pop()
        for block in blocks:
            event_type = "message"
            data_lines: list[str] = []
            for line in block.splitlines():
                if line.startswith("event:"):
                    event_type = line[6:].strip()
                elif line.startswith("data:"):
                    data_lines.append(line[5:].lstrip())
            if data_lines:
                yield event_type, "\n".join(data_lines)


def event_has_content(event_type: str, data: str) -> bool:
    if event_type != "message" or data == "[DONE]":
        return False
    try:
        payload = json.loads(data)
    except json.JSONDecodeError:
        return False
    return bool(payload.get("choices", [{}])[0].get("delta", {}).get("content"))


async def run_live_once(
    backend_url: str,
    token: str,
    prompt: str,
    prompt_kind: str,
    timeout: float,
) -> RunMetrics:
    started = time.perf_counter()
    first_event_ms: float | None = None
    first_visible_status_ms: float | None = None
    first_content_ms: float | None = None
    event_counts: dict[str, int] = {}
    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "messages": [{"role": "user", "content": prompt}],
        "conversation_id": f"latency-benchmark-{int(time.time() * 1000)}",
        "use_rag": False,
        "use_web_search": False,
        "force_think": False,
        "max_tokens": 256,
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "POST", f"{backend_url.rstrip('/')}/api/v1/stream", headers=headers, json=payload
        ) as response:
            response.raise_for_status()
            async for event_type, data in iter_sse_events(response):
                now_ms = _elapsed_ms(started)
                first_event_ms = first_event_ms if first_event_ms is not None else now_ms
                event_counts[event_type] = event_counts.get(event_type, 0) + 1
                if event_type in {"status", "action", "tool_started", "warning"}:
                    if first_visible_status_ms is None:
                        first_visible_status_ms = now_ms
                if first_content_ms is None and event_has_content(event_type, data):
                    first_content_ms = now_ms
                if data == "[DONE]":
                    break

    completed_ms = _elapsed_ms(started)
    if first_event_ms is None:
        raise RuntimeError("Live stream returned no SSE events")
    if first_content_ms is None:
        raise RuntimeError("Live stream returned no answer content")
    return RunMetrics(
        mode="live",
        variant="baseline",
        prompt_kind=prompt_kind,
        first_event_ms=first_event_ms,
        first_visible_status_ms=first_visible_status_ms,
        main_model_start_ms=None,
        first_content_ms=first_content_ms,
        completed_ms=completed_ms,
        completion_calls=0,
        embedding_calls=0,
        memory_queries=0,
        event_counts=event_counts,
    )


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# AREQA Chat Latency Benchmark",
        "",
        f"Mode: `{report['mode']}`  ",
        f"Measured runs: `{len(report['runs'])}`",
        "",
        "| Variant | Runs | First content median | First content p95 | Completed median | Visible status | TTFT improvement |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for variant, metrics in report["summary"].items():
        visible = metrics["first_visible_status_median_ms"]
        visible_text = f"{visible:.2f} ms" if visible is not None else "none"
        improvement = metrics.get("ttft_improvement_percent", 0.0)
        lines.append(
            f"| {variant} | {metrics['runs']} | {metrics['first_content_median_ms']:.2f} ms "
            f"| {metrics['first_content_p95_ms']:.2f} ms | {metrics['completed_median_ms']:.2f} ms "
            f"| {visible_text} | {improvement:.2f}% |"
        )
    lines.extend(
        [
            "",
            "> Mock results validate the experiment mechanics only; they are not production latency measurements."
            if report["mode"] == "mocked"
            else "> Live results measure client-visible SSE timings; internal phase attribution requires server instrumentation.",
            "",
        ]
    )
    return "\n".join(lines)


async def run_benchmark(args: argparse.Namespace) -> dict[str, Any]:
    runs: list[RunMetrics] = []
    if args.mode == "mocked":
        for variant in VARIANTS:
            for index in range(args.warmup + args.runs):
                sample = await run_mock_once(variant, "general")
                if index >= args.warmup:
                    runs.append(sample)
    else:
        if not args.backend_url or not args.token:
            raise RuntimeError("Live mode requires --backend-url and --token (or matching environment variables)")
        for index in range(args.warmup + args.runs):
            prompt_index = index % len(DEFAULT_PROMPTS)
            sample = await run_live_once(
                args.backend_url,
                args.token,
                DEFAULT_PROMPTS[prompt_index],
                ("general", "explicit_recall", "sensitive")[prompt_index],
                args.timeout,
            )
            if index >= args.warmup:
                runs.append(sample)

    return {
        "schema_version": 1,
        "mode": args.mode,
        "generated_at_epoch": int(time.time()),
        "configuration": {"runs": args.runs, "warmup": args.warmup},
        "summary": summarize(runs),
        "runs": [asdict(run) for run in runs],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("mocked", "live"), default="mocked")
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--backend-url", default=os.environ.get("BACKEND_API_URL", ""))
    parser.add_argument("--token", default=os.environ.get("BENCHMARK_AUTH_TOKEN", ""))
    parser.add_argument("--output", type=Path, default=Path("/tmp/areqa-latency.json"))
    args = parser.parse_args()
    if args.runs < 1 or args.warmup < 0:
        parser.error("--runs must be >= 1 and --warmup must be >= 0")
    return args


def main() -> int:
    load_dotenv()
    args = parse_args()
    try:
        report = asyncio.run(run_benchmark(args))
    except (httpx.HTTPError, RuntimeError) as exc:
        print(f"Benchmark failed: {exc}")
        return 1

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
