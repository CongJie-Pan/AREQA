import asyncio

import pytest

from backend.services.turn_latency_trace import TurnLatencyTrace


def test_turn_latency_trace_snapshot_uses_safe_metadata_only():
    trace = TurnLatencyTrace(run_id="run-1", conversation_id="conversation-1")

    trace.mark("Prompt Assembly Started")
    trace.increment_model_call("policy classifier")
    trace.increment_tool_call("web search", "cache hit")
    snapshot = trace.snapshot()

    assert snapshot["run_id"] == "run-1"
    assert snapshot["conversation_id"] == "conversation-1"
    assert snapshot["phases"][0]["name"] == "prompt_assembly_started"
    assert snapshot["model_calls"] == {"policy_classifier": 1}
    assert snapshot["tool_calls"] == {"web_search": 1}
    assert snapshot["cache_statuses"] == {"web_search:cache_hit": 1}
    assert "raw_message" not in snapshot
    assert "prompt" not in snapshot


def test_turn_latency_trace_mark_once_records_first_occurrence_only():
    trace = TurnLatencyTrace(run_id="run-1", conversation_id="conversation-1")

    trace.mark_once("first_answer_delta")
    trace.mark_once("first_answer_delta")

    phases = [phase["name"] for phase in trace.snapshot()["phases"]]
    assert phases == ["first_answer_delta"]


@pytest.mark.asyncio
async def test_turn_latency_trace_measure_records_success_and_failure():
    success = TurnLatencyTrace(run_id="run-1", conversation_id="conversation-1")

    async with success.measure("hot memory"):
        await asyncio.sleep(0)

    assert [phase["name"] for phase in success.snapshot()["phases"]] == [
        "hot_memory_started",
        "hot_memory_finished",
    ]

    failure = TurnLatencyTrace(run_id="run-2", conversation_id="conversation-2")
    with pytest.raises(RuntimeError):
        async with failure.measure("long term memory"):
            raise RuntimeError("boom")

    assert [phase["name"] for phase in failure.snapshot()["phases"]] == [
        "long_term_memory_started",
        "long_term_memory_failed",
    ]
