import json

import pytest

from backend.core import AgentEvent, ConversationRuntime, EventType, RunContext, SSEAdapter, SearchMode


def test_run_context_rejects_empty_scope_identifiers():
    with pytest.raises(ValueError, match="user_id"):
        RunContext("run-1", "", "conversation-1", "request-1", SearchMode.NEVER)


def test_sse_adapter_preserves_legacy_payload_and_adds_runtime_metadata():
    encoded = SSEAdapter().encode(AgentEvent(
        EventType.METADATA, {"promptTokens": 12}, "run-1", 1
    ))

    event_line, data_line = encoded.strip().splitlines()
    assert event_line == "event: metadata"
    assert json.loads(data_line.removeprefix("data: ")) == {
        "promptTokens": 12,
        "runId": "run-1",
        "schemaVersion": 1,
    }


def test_sse_adapter_requires_strictly_increasing_sequences():
    adapter = SSEAdapter()
    adapter.encode(AgentEvent(EventType.STATUS, {}, "run-1", 2))
    with pytest.raises(ValueError, match="strictly increasing"):
        adapter.encode(AgentEvent(EventType.STATUS, {}, "run-1", 2))


def test_sse_adapter_rejects_events_after_terminal_event():
    adapter = SSEAdapter()
    adapter.encode(AgentEvent(EventType.DONE, {}, "run-1", 1))
    with pytest.raises(ValueError, match="after a terminal"):
        adapter.encode(AgentEvent(EventType.STATUS, {}, "run-1", 2))


def test_sse_adapter_allows_done_sentinel_after_legacy_terminal_event():
    adapter = SSEAdapter()
    adapter.encode_legacy('event: done\ndata: {"suggestions": []}\n\n', "run-1")

    assert adapter.encode_legacy("data: [DONE]\n\n", "run-1") == "data: [DONE]\n\n"


def test_sse_adapter_rejects_legacy_business_event_after_terminal_event():
    adapter = SSEAdapter()
    adapter.encode_legacy('event: done\ndata: {"suggestions": []}\n\n', "run-1")

    with pytest.raises(ValueError, match="after a terminal"):
        adapter.encode_legacy(
            'event: status\ndata: {"status": "generating"}\n\n',
            "run-1",
        )


def test_sse_adapter_does_not_sequence_heartbeats():
    adapter = SSEAdapter()
    assert adapter.encode_legacy(": heartbeat\n\n", "run-1") == ": heartbeat\n\n"
    assert adapter.encode(AgentEvent(EventType.STATUS, {}, "run-1", 1))


def test_legacy_answer_delta_participates_in_typed_sequence():
    adapter = SSEAdapter()
    block = 'data: {"choices":[{"delta":{"content":"hello"}}]}\n\n'
    assert adapter.encode_legacy(block, "run-1") == block

    with pytest.raises(ValueError, match="strictly increasing"):
        adapter.encode(AgentEvent(EventType.STATUS, {}, "run-1", 1))


def test_runtime_creates_isolated_sessions_and_ephemeral_conversation_scope():
    runtime = ConversationRuntime()
    first = runtime.start_session(
        user_id="user-1",
        conversation_id="",
        request_id=None,
        search_mode=SearchMode.NEVER,
    )
    second = runtime.start_session(
        user_id="user-1",
        conversation_id="conversation-2",
        request_id=" request-2 ",
        search_mode=SearchMode.ALWAYS,
    )

    assert first.context.conversation_id.startswith("ephemeral:")
    assert first.context.request_id == first.context.run_id
    assert second.context.request_id == "request-2"
    assert first.state is not second.state
    assert first.transport is not second.transport


def test_runtime_isolates_one_hundred_concurrent_session_states():
    runtime = ConversationRuntime()
    sessions = [
        runtime.start_session(
            user_id=f"user-{index}",
            conversation_id=f"conversation-{index}",
            request_id=None,
            search_mode=SearchMode.AUTO,
        )
        for index in range(100)
    ]

    assert len({session.context.run_id for session in sessions}) == 100
    assert len({id(session.state) for session in sessions}) == 100
    sessions[0].state.context_prompt = "private-source"
    assert all(not session.state.context_prompt for session in sessions[1:])
