import asyncio
import logging
from unittest.mock import AsyncMock

import pytest

from backend.services.post_turn_service import PostTurnService
from backend.services.turn_latency_trace import TurnLatencyTrace


@pytest.mark.asyncio
async def test_queue_post_turn_work_is_non_blocking_and_bounded(caplog):
    """Slow durable dispatch must not delay or outlive its configured bound."""

    caplog.set_level(logging.INFO)
    blocker = asyncio.Event()
    service = PostTurnService()

    async def wait_for_release(**_kwargs):
        await blocker.wait()

    service.dispatch_post_turn_work = AsyncMock(side_effect=wait_for_release)

    task = service.queue_post_turn_work(
        timeout_seconds=0.01,
        run_id="run-1",
        conversation_id="conversation-1",
    )

    assert task.done() is False
    await task
    assert "orchestration.post_turn_timeout" in caplog.text


@pytest.mark.asyncio
async def test_suggestion_events_record_trace_markers():
    suggestion_service = AsyncMock()
    suggestion_service.generate_suggestions.return_value = ["問題一？"]
    service = PostTurnService(suggestion_service)
    trace = TurnLatencyTrace(run_id="run-1", conversation_id="conversation-1")

    events = await service.suggestion_events(
        last_user_msg="請解釋 dependency injection",
        answer_text="answer",
        context_results_obj=None,
        use_rag=False,
        use_web_search=False,
        trace=trace,
    )

    joined = "".join(events)
    snapshot = trace.snapshot()
    phase_names = [phase["name"] for phase in snapshot["phases"]]
    assert "event: suggestions" in joined
    assert "event: done" in joined
    assert "suggestions_started" in phase_names
    assert "suggestions_finished" in phase_names
    assert snapshot["model_calls"] == {"suggestions": 1}


@pytest.mark.asyncio
async def test_suggestion_events_timeout_returns_compatible_done(caplog):
    """Slow suggestions must fall back without blocking terminal completion."""

    caplog.set_level(logging.WARNING)
    blocker = asyncio.Event()
    suggestion_service = AsyncMock()

    async def slow_suggestions(**_kwargs):
        await blocker.wait()
        return ["太晚的問題？"]

    suggestion_service.generate_suggestions.side_effect = slow_suggestions
    service = PostTurnService(suggestion_service)
    trace = TurnLatencyTrace(run_id="run-1", conversation_id="conversation-1")

    events = await service.suggestion_events(
        last_user_msg="請解釋 dependency injection",
        answer_text="answer",
        context_results_obj=None,
        use_rag=False,
        use_web_search=False,
        timeout_ms=1,
        trace=trace,
    )

    joined = "".join(events)
    phase_names = [phase["name"] for phase in trace.snapshot()["phases"]]
    assert "event: suggestions" not in joined
    assert 'event: done\ndata: {"suggestions": []}' in joined
    assert "suggestions_started" in phase_names
    assert "suggestions_timeout" in phase_names
    assert "orchestration.suggestions_timeout" in caplog.text
