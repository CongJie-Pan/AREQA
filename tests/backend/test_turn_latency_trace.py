import asyncio

import pytest

from backend.services.turn_latency_trace import PhaseTiming, TurnLatencyTrace


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


def test_turn_latency_trace_diagnostic_summary_identifies_slow_phase():
    trace = TurnLatencyTrace(run_id="run-1", conversation_id="conversation-1")
    trace._phases = [
        PhaseTiming("request_accepted", 0),
        PhaseTiming("prompt_assembly_started", 100),
        PhaseTiming("long_term_memory_started", 150),
        PhaseTiming("long_term_memory_finished", 2300),
        PhaseTiming("prompt_assembly_finished", 2400),
        PhaseTiming("main_model_started", 2500),
        PhaseTiming("first_answer_delta", 7200),
        PhaseTiming("main_model_finished", 7800),
        PhaseTiming("terminal_sent", 8200),
    ]
    trace.increment_model_call("main_answer")
    trace.increment_tool_call("memory_query")

    summary = trace.diagnostic_summary(
        slow_total_threshold_ms=8000,
        slow_first_token_threshold_ms=5000,
        top_phase_count=2,
    )

    assert summary["time_to_first_answer_ms"] == 7200
    assert summary["provider_first_token_ms"] == 4700
    assert summary["phase_durations_ms"]["prompt_assembly"] == 2300
    assert summary["phase_durations_ms"]["long_term_memory"] == 2150
    assert summary["phase_durations_ms"]["main_model"] == 5300
    assert summary["top_phase_durations"][0] == {
        "name": "main_model",
        "duration_ms": 5300,
    }
    assert summary["model_calls"] == {"main_answer": 1}
    assert summary["tool_calls"] == {"memory_query": 1}
    assert summary["is_slow"] is True
    assert "total_elapsed" in summary["slow_reasons"]


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
