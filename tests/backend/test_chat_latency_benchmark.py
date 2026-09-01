import importlib.util
from pathlib import Path
import sys

import httpx
import pytest


SCRIPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "performance"
    / "benchmark_chat_latency.py"
)
SPEC = importlib.util.spec_from_file_location("benchmark_chat_latency", SCRIPT_PATH)
assert SPEC and SPEC.loader
benchmark = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = benchmark
SPEC.loader.exec_module(benchmark)


def test_percentile_interpolates_and_validates_empty_input():
    assert benchmark.percentile([10.0, 20.0, 30.0], 0.5) == 20.0
    assert benchmark.percentile([10.0, 20.0], 0.95) == pytest.approx(19.5)
    with pytest.raises(ValueError, match="at least one"):
        benchmark.percentile([], 0.95)


@pytest.mark.asyncio
async def test_mock_experiment_isolates_preflight_latency():
    baseline = await benchmark.run_mock_once("baseline", "general")
    no_policy = await benchmark.run_mock_once("no_policy_wait", "general")
    no_cold = await benchmark.run_mock_once("no_cold_memory", "general")
    optimized = await benchmark.run_mock_once("optimized", "general")

    assert baseline.first_content_ms > no_policy.first_content_ms
    assert baseline.first_content_ms > no_cold.first_content_ms
    assert no_policy.first_content_ms > optimized.first_content_ms
    assert no_cold.first_content_ms > optimized.first_content_ms
    assert baseline.completion_calls == 3
    assert optimized.completion_calls == 1
    assert baseline.embedding_calls == 1
    assert optimized.embedding_calls == 0
    assert baseline.first_visible_status_ms is None
    assert optimized.first_visible_status_ms is not None
    assert optimized.first_visible_status_ms < optimized.first_content_ms


def test_summary_reports_improvement_against_baseline():
    runs = [
        benchmark.RunMetrics(
            mode="mocked",
            variant="baseline",
            prompt_kind="general",
            first_event_ms=1.0,
            first_visible_status_ms=None,
            main_model_start_ms=80.0,
            first_content_ms=100.0,
            completed_ms=130.0,
            completion_calls=3,
            embedding_calls=1,
            memory_queries=2,
            event_counts={"metadata": 1},
        ),
        benchmark.RunMetrics(
            mode="mocked",
            variant="optimized",
            prompt_kind="general",
            first_event_ms=1.0,
            first_visible_status_ms=2.0,
            main_model_start_ms=30.0,
            first_content_ms=50.0,
            completed_ms=80.0,
            completion_calls=1,
            embedding_calls=0,
            memory_queries=0,
            event_counts={"status": 1},
        ),
    ]

    summary = benchmark.summarize(runs)

    assert summary["optimized"]["ttft_improvement_percent"] == 50.0
    assert summary["baseline"]["first_visible_status_median_ms"] is None
    assert summary["optimized"]["first_visible_status_median_ms"] == 2.0


@pytest.mark.asyncio
async def test_sse_parser_handles_split_chunks_and_content_detection():
    class FakeResponse:
        async def aiter_text(self):
            yield "event: status\ndata: {\"status\": \"preparing\"}\n"
            yield "\ndata: {\"choices\": [{\"delta\": {\"content\": \"回答\"}}]}\n\n"

    events = [event async for event in benchmark.iter_sse_events(FakeResponse())]

    assert events[0][0] == "status"
    assert events[1][0] == "message"
    assert benchmark.event_has_content(*events[1]) is True
    assert benchmark.event_has_content("metadata", "{}") is False


@pytest.mark.asyncio
async def test_live_run_allows_anonymous_stream_and_records_event_first_seen(monkeypatch):
    captured_headers = {}

    class FakeStreamResponse:
        def raise_for_status(self):
            return None

        async def aiter_text(self):
            yield "event: metadata\ndata: {}\n\n"
            yield "event: status\ndata: {\"status\": \"routing\"}\n\n"
            yield "data: {\"choices\": [{\"delta\": {\"content\": \"answer\"}}]}\n\n"
            yield "data: [DONE]\n\n"

    class FakeStreamContext:
        async def __aenter__(self):
            return FakeStreamResponse()

        async def __aexit__(self, exc_type, exc, tb):
            return False

    class FakeAsyncClient:
        def __init__(self, timeout):
            self.timeout = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def stream(self, method, url, headers, json):
            captured_headers.update(headers)
            return FakeStreamContext()

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    metrics = await benchmark.run_live_once(
        "http://backend.test",
        None,
        "請簡短回答",
        "general",
        5.0,
    )

    assert "Authorization" not in captured_headers
    assert captured_headers["X-Request-ID"].startswith("latency-benchmark-")
    assert metrics.first_content_ms >= metrics.first_event_ms
    assert metrics.event_counts["status"] == 1
    assert metrics.event_first_seen_ms
    assert "metadata" in metrics.event_first_seen_ms


def test_markdown_report_distinguishes_mock_results_from_production_data():
    report = {
        "mode": "mocked",
        "runs": [{}],
        "summary": {
            "baseline": {
                "runs": 1,
                "first_content_median_ms": 100.0,
                "first_content_p95_ms": 100.0,
                "completed_median_ms": 120.0,
                "first_visible_status_median_ms": None,
                "ttft_improvement_percent": 0.0,
            }
        },
    }

    rendered = benchmark.render_markdown(report)

    assert "not production latency measurements" in rendered
    assert "| baseline |" in rendered
