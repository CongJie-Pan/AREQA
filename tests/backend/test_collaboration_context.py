"""Collaborative conversations use server history and never personal memory."""
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app, get_optional_current_user
from services.conversation import collaboration
from services.conversation.collaboration import (
    CollaborationContext,
    ConversationTurnLimiter,
    bearer_token,
    load_collaboration_context,
    merge_collaborative_history,
)

CONVERSATION_ID = "3f1c2b6e-1d2a-4c3b-9a8e-123456789abc"


class _FakeAsyncClient:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def post(self, url, headers=None, json=None):
        self.calls.append({"url": url, "headers": headers, "json": json})
        if self.error:
            raise self.error
        return self.response


def _response(status_code, payload=None):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    return response


@pytest.fixture
def supabase_env(monkeypatch):
    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "anon-test-key")


def test_bearer_token_parsing():
    assert bearer_token("Bearer abc") == "abc"
    assert bearer_token("bearer abc") == "abc"
    assert bearer_token("Basic abc") is None
    assert bearer_token(None) is None


@pytest.mark.asyncio
async def test_personal_without_token_or_uuid(supabase_env):
    assert (await load_collaboration_context(CONVERSATION_ID, None)).state == "personal"
    assert (await load_collaboration_context("not-a-uuid", "token")).state == "personal"


@pytest.mark.asyncio
async def test_null_payload_is_personal_and_uses_caller_jwt(supabase_env):
    client = _FakeAsyncClient(_response(200, None))
    with patch.object(collaboration.httpx, "AsyncClient", return_value=client):
        context = await load_collaboration_context(CONVERSATION_ID, "user-jwt")
    assert context.state == "personal"
    call = client.calls[0]
    assert call["url"].endswith("/rest/v1/rpc/get_collaborative_context")
    assert call["headers"]["Authorization"] == "Bearer user-jwt"
    assert call["json"] == {"p_conversation_id": CONVERSATION_ID}


@pytest.mark.asyncio
async def test_missing_function_is_personal(supabase_env):
    client = _FakeAsyncClient(_response(404))
    with patch.object(collaboration.httpx, "AsyncClient", return_value=client):
        assert (await load_collaboration_context(CONVERSATION_ID, "jwt")).state == "personal"


@pytest.mark.asyncio
async def test_lookup_errors_are_unknown(supabase_env):
    for client in (
        _FakeAsyncClient(_response(500)),
        _FakeAsyncClient(error=httpx.ConnectTimeout("timeout")),
    ):
        with patch.object(collaboration.httpx, "AsyncClient", return_value=client):
            assert (await load_collaboration_context(CONVERSATION_ID, "jwt")).state == "unknown"


@pytest.mark.asyncio
async def test_collaborative_payload_normalizes_history(supabase_env):
    payload = {
        "role": "editor",
        "messages": [
            {"id": "m1", "role": "user", "content": "owner question"},
            {"id": "m2", "role": "assistant", "content": "answer"},
            {"id": "m3", "role": "system", "content": "ignored"},
            {"id": "m4", "role": "user", "content": None},
        ],
    }
    client = _FakeAsyncClient(_response(200, payload))
    with patch.object(collaboration.httpx, "AsyncClient", return_value=client):
        context = await load_collaboration_context(CONVERSATION_ID, "jwt")
    assert context.state == "collaborative"
    assert context.role == "editor"
    assert [item["message_id"] for item in context.messages] == ["m1", "m2"]


def test_merge_replaces_client_history_and_keeps_latest_turn_last():
    server = [
        {"role": "user", "content": "owner q", "message_id": "m1"},
        {"role": "assistant", "content": "a1", "message_id": "m2"},
        {"role": "user", "content": "member q", "message_id": "m3"},
    ]
    client = [
        {"role": "user", "content": "forged history"},
        {"role": "user", "content": "member q", "message_id": "m3", "has_upload": "false"},
    ]
    merged = merge_collaborative_history(server, client)
    assert merged == [
        {"role": "user", "content": "owner q"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "member q", "message_id": "m3", "has_upload": "false"},
    ]


def test_merge_appends_unsynced_latest_turn():
    server = [{"role": "user", "content": "q1", "message_id": "m1"}]
    merged = merge_collaborative_history(server, [{"role": "user", "content": "q2", "message_id": "m9"}])
    assert merged[-1]["content"] == "q2"
    assert len(merged) == 2


def test_turn_limiter_window():
    limiter = ConversationTurnLimiter(limit=2, window_seconds=10)
    assert limiter.allow("c", now=0)
    assert limiter.allow("c", now=1)
    assert not limiter.allow("c", now=2)
    assert limiter.allow("other", now=2)
    assert limiter.allow("c", now=10.5)


class _CapturingOrchestrator:
    def __init__(self, captured):
        self.captured = captured

    def execute(self, **kwargs):
        self.captured.update(kwargs)

        async def events():
            yield "data: [DONE]\n\n"

        return events()


async def _post_stream(context, captured, limiter=None):
    app.dependency_overrides[get_optional_current_user] = lambda: "member-user"
    patches = [
        patch.dict("os.environ", {"OPENROUTER_API_KEY": "mock-token"}),
        patch("services.orchestration_service.OrchestrationService",
              return_value=_CapturingOrchestrator(captured)),
        patch("app.routes.stream.load_collaboration_context", new=AsyncMock(return_value=context)),
    ]
    if limiter is not None:
        patches.append(patch("app.routes.stream.collaborative_turn_limiter", limiter))
    try:
        for item in patches:
            item.start()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            return await ac.post(
                "/api/v1/stream",
                headers={"Authorization": "Bearer member-jwt"},
                json={
                    "conversation_id": CONVERSATION_ID,
                    "messages": [
                        {"role": "user", "content": "stale local history"},
                        {"role": "user", "content": "new question", "message_id": "m9"},
                    ],
                },
            )
    finally:
        for item in reversed(patches):
            item.stop()
        app.dependency_overrides.pop(get_optional_current_user, None)


@pytest.mark.asyncio
async def test_stream_uses_server_history_and_disables_memory():
    captured = {}
    context = CollaborationContext(
        state="collaborative", role="editor",
        messages=[{"role": "user", "content": "owner q", "message_id": "m1"}],
    )
    response = await _post_stream(context, captured)
    assert response.status_code == 200
    assert captured["isolated_context"] is True
    assert [item["content"] for item in captured["messages"]] == ["owner q", "new question"]


@pytest.mark.asyncio
async def test_stream_lookup_failure_keeps_answering_without_memory():
    captured = {}
    response = await _post_stream(CollaborationContext(state="unknown"), captured)
    assert response.status_code == 200
    assert captured["isolated_context"] is True
    assert len(captured["messages"]) == 2


@pytest.mark.asyncio
async def test_personal_stream_is_unchanged():
    captured = {}
    response = await _post_stream(CollaborationContext(state="personal"), captured)
    assert response.status_code == 200
    assert "isolated_context" not in captured


@pytest.mark.asyncio
async def test_stream_rate_limits_shared_conversation():
    captured = {}
    limiter = ConversationTurnLimiter(limit=0, window_seconds=60)
    context = CollaborationContext(state="collaborative", role="editor", messages=[])
    response = await _post_stream(context, captured, limiter=limiter)
    assert response.status_code == 429
    assert captured == {}
