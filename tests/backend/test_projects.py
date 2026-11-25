"""Projects: shared instructions and memory reach the prompt; lookups fail soft."""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app, get_current_user, get_optional_current_user
from services.conversation import projects
from services.conversation.collaboration import CollaborationContext
from services.conversation.projects import (
    ProjectContext,
    apply_project_prompt,
    generate_project_memory,
    load_project_context,
    render_project_prompt,
)

PROJECT_ID = "7a1c2b6e-1d2a-4c3b-9a8e-123456789abc"
CONVERSATION_ID = "3f1c2b6e-1d2a-4c3b-9a8e-123456789abc"


class _FakeAsyncClient:
    def __init__(self, responses=None, error=None):
        self.responses = list(responses or [])
        self.error = error
        self.calls = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def _respond(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        if self.error:
            raise self.error
        return self.responses.pop(0)

    async def get(self, url, headers=None, params=None):
        return await self._respond("GET", url, headers=headers, params=params)

    async def patch(self, url, headers=None, params=None, json=None):
        return await self._respond("PATCH", url, headers=headers, params=params, json=json)


def _response(status_code, payload=None):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    return response


def _row(**overrides):
    row = {
        "id": PROJECT_ID, "name": "Diary", "instructions": "Answer briefly.",
        "use_account_memory": True, "memory_summary": "Master's student keeping a diary.",
        "memory_details": ["Writes every night", 3, ""], "memory_updated_at": "2026-11-23T00:00:00+00:00",
    }
    row.update(overrides)
    return row


@pytest.fixture
def supabase_env(monkeypatch):
    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "anon-test-key")


@pytest.mark.asyncio
async def test_lookup_skips_invalid_ids_and_missing_tokens(supabase_env):
    assert (await load_project_context("not-a-uuid", "jwt")).state == "none"
    assert (await load_project_context(PROJECT_ID, None)).state == "none"


@pytest.mark.asyncio
async def test_lookup_uses_caller_jwt_and_cleans_details(supabase_env):
    client = _FakeAsyncClient([_response(200, [_row()])])
    with patch.object(projects.httpx, "AsyncClient", return_value=client):
        context = await load_project_context(PROJECT_ID, "user-jwt")
    assert context.state == "loaded"
    assert context.memory_details == ["Writes every night"]
    call = client.calls[0]
    assert call["url"].endswith("/rest/v1/projects")
    assert call["headers"]["Authorization"] == "Bearer user-jwt"
    assert call["params"]["id"] == f"eq.{PROJECT_ID}"


@pytest.mark.asyncio
async def test_lookup_states_for_missing_rows_table_and_errors(supabase_env):
    cases = [
        (_FakeAsyncClient([_response(200, [])]), "none"),
        (_FakeAsyncClient([_response(404)]), "none"),
        (_FakeAsyncClient([_response(500)]), "unknown"),
        (_FakeAsyncClient(error=httpx.ConnectTimeout("timeout")), "unknown"),
    ]
    for client, expected in cases:
        with patch.object(projects.httpx, "AsyncClient", return_value=client):
            assert (await load_project_context(PROJECT_ID, "jwt")).state == expected


def test_render_includes_instructions_and_memory_only_when_present():
    loaded = ProjectContext(state="loaded", name="Diary", instructions="Answer briefly.",
                            memory_summary="Keeps a diary.", memory_details=["Writes nightly"])
    overlay = render_project_prompt(loaded)
    assert "Diary" in overlay and "Answer briefly." in overlay and "- Writes nightly" in overlay
    assert render_project_prompt(ProjectContext(state="loaded", name="Empty")) == ""
    assert render_project_prompt(ProjectContext(state="unknown", instructions="x")) == ""


def test_apply_appends_to_system_prompt_without_mutating_input():
    messages = [{"role": "system", "content": "BASE"}, {"role": "user", "content": "hi"}]
    result = apply_project_prompt(messages, "\n\nPROJECT")
    assert result[0]["content"] == "BASE\n\nPROJECT"
    assert messages[0]["content"] == "BASE"
    assert apply_project_prompt(messages, "") is messages
    assert apply_project_prompt([{"role": "user", "content": "hi"}], "\n\nP")[0] == {"role": "system", "content": "P"}


@pytest.mark.asyncio
async def test_generate_memory_parses_fenced_json_and_bounds_details():
    payload = {"summary": "s", "details": [f"d{i}" for i in range(20)]}
    completion = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(
        content=f"```json\n{json.dumps(payload)}\n```"))])
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(return_value=completion))))
    summary, details = await generate_project_memory(
        client, "model", project_name="Diary", transcript="",
        previous=ProjectContext(state="loaded", memory_summary="old"), instruction="drop the dorm detail",
    )
    assert summary == "s"
    assert len(details) == projects.MAX_MEMORY_DETAILS
    prompt = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
    assert "drop the dorm detail" in prompt and "old" in prompt


class _CapturingOrchestrator:
    def __init__(self, captured):
        self.captured = captured

    def execute(self, **kwargs):
        self.captured.update(kwargs)

        async def events():
            yield "data: [DONE]\n\n"

        return events()


async def _post_stream(project_context, captured, body_extra=None):
    app.dependency_overrides[get_optional_current_user] = lambda: "owner-user"
    patches = [
        patch.dict("os.environ", {"OPENROUTER_API_KEY": "mock-token"}),
        patch("services.orchestration_service.OrchestrationService",
              return_value=_CapturingOrchestrator(captured)),
        patch("app.routes.stream.load_collaboration_context",
              new=AsyncMock(return_value=CollaborationContext(state="personal"))),
        patch("app.routes.stream.load_project_context", new=AsyncMock(return_value=project_context)),
    ]
    try:
        for item in patches:
            item.start()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            return await ac.post(
                "/api/v1/stream",
                headers={"Authorization": "Bearer owner-jwt"},
                json={
                    "conversation_id": CONVERSATION_ID,
                    "messages": [{"role": "user", "content": "hello"}],
                    **(body_extra or {}),
                },
            )
    finally:
        for item in reversed(patches):
            item.stop()
        app.dependency_overrides.pop(get_optional_current_user, None)


@pytest.mark.asyncio
async def test_stream_passes_project_prompt_and_keeps_account_memory():
    captured = {}
    context = ProjectContext(state="loaded", name="Diary", instructions="Answer briefly.")
    response = await _post_stream(context, captured, {"project_id": PROJECT_ID})
    assert response.status_code == 200
    assert "Answer briefly." in captured["project_prompt"]
    assert "isolated_context" not in captured


@pytest.mark.asyncio
async def test_stream_isolates_memory_when_project_turns_account_memory_off():
    captured = {}
    context = ProjectContext(state="loaded", name="Diary", instructions="x", use_account_memory=False)
    response = await _post_stream(context, captured, {"project_id": PROJECT_ID})
    assert response.status_code == 200
    assert captured["isolated_context"] is True


@pytest.mark.asyncio
async def test_stream_without_project_or_failed_lookup_adds_nothing():
    for body, context in (({}, ProjectContext(state="loaded", instructions="x")),
                          ({"project_id": PROJECT_ID}, ProjectContext(state="unknown"))):
        captured = {}
        response = await _post_stream(context, captured, body)
        assert response.status_code == 200
        assert "project_prompt" not in captured
        assert "isolated_context" not in captured


@pytest.mark.asyncio
async def test_revise_route_saves_generated_memory():
    app.dependency_overrides[get_current_user] = lambda: "owner-user"
    loaded = ProjectContext(state="loaded", project_id=PROJECT_ID, name="Diary", memory_summary="old")
    saved = ProjectContext(state="loaded", project_id=PROJECT_ID, memory_summary="new", memory_details=["d"],
                           memory_updated_at="2026-11-25T00:00:00+00:00")
    save = AsyncMock(return_value=saved)
    try:
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "k"}), \
             patch("app.routes.projects.load_project_context", new=AsyncMock(return_value=loaded)), \
             patch("app.routes.projects.generate_project_memory", new=AsyncMock(return_value=("new", ["d"]))), \
             patch("app.routes.projects.save_project_memory", new=save):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.post(
                    f"/api/v1/projects/{PROJECT_ID}/memory/revise",
                    headers={"Authorization": "Bearer owner-jwt"},
                    json={"instruction": "shorter"},
                )
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert response.status_code == 200
    assert response.json()["memory"] == {"summary": "new", "details": ["d"], "updated_at": "2026-11-25T00:00:00+00:00"}
    save.assert_awaited_once_with(PROJECT_ID, "owner-jwt", "new", ["d"])


@pytest.mark.asyncio
async def test_refresh_route_rejects_projects_the_caller_cannot_read():
    app.dependency_overrides[get_current_user] = lambda: "other-user"
    try:
        with patch("app.routes.projects.load_project_context",
                   new=AsyncMock(return_value=ProjectContext(state="none"))):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.post(
                    f"/api/v1/projects/{PROJECT_ID}/memory/refresh",
                    headers={"Authorization": "Bearer other-jwt"},
                )
    finally:
        app.dependency_overrides.pop(get_current_user, None)
    assert response.status_code == 404
