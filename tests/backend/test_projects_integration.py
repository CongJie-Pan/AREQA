"""Projects integration: stream route → Supabase lookup → orchestration → assembled prompt,
and the memory refresh route end to end over a fake PostgREST and a fake model.

Only the network edges (httpx to Supabase, the OpenRouter client) are faked; the
route, the project service and prompt preparation run for real.
"""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app, get_current_user, get_optional_current_user
from services.conversation import projects
from services.conversation.collaboration import CollaborationContext
from services.orchestration import answer_preparation
from services.query_policy.models import AttachmentTask

PROJECT_ID = "7a1c2b6e-1d2a-4c3b-9a8e-123456789abc"
CONVERSATION_ID = "3f1c2b6e-1d2a-4c3b-9a8e-123456789abc"


def _response(status_code, payload=None):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    return response


class _FakePostgrest:
    """Answers PostgREST calls by table and method; records every request."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, *_args, **_kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return False

    async def _handle(self, method, url, **kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        table = url.rsplit("/rest/v1/", 1)[-1]
        return self.routes[(method, table)](kwargs)

    async def get(self, url, headers=None, params=None):
        return await self._handle("GET", url, headers=headers, params=params)

    async def patch(self, url, headers=None, params=None, json=None):
        return await self._handle("PATCH", url, headers=headers, params=params, json=json)


def _project_row(**overrides):
    row = {
        "id": PROJECT_ID, "name": "Diary", "instructions": "Always answer in two sentences.",
        "use_account_memory": True, "memory_summary": "Master's student who journals nightly.",
        "memory_details": ["Lives in a Taipei dorm"], "memory_updated_at": "2026-11-23T00:00:00+00:00",
    }
    row.update(overrides)
    return row


@pytest.fixture
def supabase_env(monkeypatch):
    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("NEXT_PUBLIC_SUPABASE_ANON_KEY", "anon-test-key")


class _CapturingOrchestrator:
    def __init__(self, captured):
        self.captured = captured

    def execute(self, **kwargs):
        self.captured.update(kwargs)

        async def events():
            yield "data: [DONE]\n\n"

        return events()


async def _stream(fake_postgrest, body):
    captured = {}
    app.dependency_overrides[get_optional_current_user] = lambda: "owner-user"
    try:
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "mock"}), \
             patch("services.orchestration_service.OrchestrationService", return_value=_CapturingOrchestrator(captured)), \
             patch("app.routes.stream.load_collaboration_context",
                   new=AsyncMock(return_value=CollaborationContext(state="personal"))), \
             patch.object(projects.httpx, "AsyncClient", fake_postgrest):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.post("/api/v1/stream", headers={"Authorization": "Bearer owner-jwt"}, json={
                    "conversation_id": CONVERSATION_ID, "messages": [{"role": "user", "content": "今天好累"}], **body,
                })
    finally:
        app.dependency_overrides.pop(get_optional_current_user, None)
    return response, captured


@pytest.mark.asyncio
async def test_project_turn_reads_project_with_caller_jwt_and_reaches_orchestration(supabase_env):
    postgrest = _FakePostgrest({("GET", "projects"): lambda _kw: _response(200, [_project_row()])})

    response, captured = await _stream(postgrest, {"project_id": PROJECT_ID})

    assert response.status_code == 200
    assert postgrest.calls[0]["headers"]["Authorization"] == "Bearer owner-jwt"
    assert postgrest.calls[0]["params"]["id"] == f"eq.{PROJECT_ID}"
    prompt = captured["project_prompt"]
    assert "Always answer in two sentences." in prompt
    assert "Master's student who journals nightly." in prompt and "- Lives in a Taipei dorm" in prompt
    assert "isolated_context" not in captured


@pytest.mark.asyncio
async def test_project_without_account_memory_isolates_the_turn(supabase_env):
    postgrest = _FakePostgrest({("GET", "projects"): lambda _kw: _response(200, [_project_row(use_account_memory=False)])})

    _response_obj, captured = await _stream(postgrest, {"project_id": PROJECT_ID})

    assert captured["isolated_context"] is True
    assert "Always answer in two sentences." in captured["project_prompt"]


@pytest.mark.asyncio
async def test_project_of_another_user_is_invisible_through_rls(supabase_env):
    # RLS returns no rows for someone else's project: the turn runs as an ordinary chat.
    postgrest = _FakePostgrest({("GET", "projects"): lambda _kw: _response(200, [])})

    response, captured = await _stream(postgrest, {"project_id": PROJECT_ID})

    assert response.status_code == 200
    assert "project_prompt" not in captured


class _FakePrepService:
    async def _node_prompt_assembly(self, *args, **kwargs):
        return [{"role": "system", "content": "AREQA BASE PROMPT"}, {"role": "user", "content": "q"}]

    def _attach_to_latest_user_message(self, messages, attachments):
        return messages

    def _add_attachment_grounding_instruction(self, messages):
        return messages

    def _add_missing_visual_attachment_instruction(self, messages, _last):
        return messages, False

    def _add_paper_auto_explain_instruction(self, messages):
        return messages


async def _prepare(monkeypatch, **extra):
    monkeypatch.setattr(answer_preparation.settings, "enable_visual_preflight", False)
    policy = SimpleNamespace(legacy_policy="DIRECT_ANSWER", attachment_task=AttachmentTask.NONE,
                             attachment_reason=SimpleNamespace(value="test"))
    messages, *_rest = await answer_preparation.prepare_answer(
        _FakePrepService(), user_id="u", conversation_id="c", messages=[{"role": "user", "content": "q"}],
        use_rag=False, use_web_search=False, force_think=False, context_results_obj=None,
        last_user_msg="q", run_state=SimpleNamespace(context_prompt=""),
        trace=SimpleNamespace(mark=lambda _name: None), turn_plan=None, turn_plan_enabled=False,
        response_policy=policy, interface_language="zh-TW", tutor_profile="general",
        response_mode="text", has_attachments=False, attachments=[], attachment_visual_sources=[],
        pdf_attachment_count=0, max_tokens=2048, **extra,
    )
    return messages


@pytest.mark.asyncio
async def test_prepared_prompt_puts_project_overlay_after_the_areqa_system_prompt(monkeypatch):
    overlay = projects.render_project_prompt(projects.ProjectContext(
        state="loaded", name="Diary", instructions="Always answer in two sentences.",
    ))

    messages = await _prepare(monkeypatch, project_prompt=overlay)

    system = messages[0]["content"]
    assert system.startswith("AREQA BASE PROMPT")
    assert system.index("AREQA BASE PROMPT") < system.index("Always answer in two sentences.")
    assert [message["role"] for message in messages] == ["system", "user"]


@pytest.mark.asyncio
async def test_memory_refresh_reads_project_chats_and_saves_the_profile(supabase_env):
    conversation_id = "11111111-1111-4111-8111-111111111111"
    saved = {}

    def save(kwargs):
        saved.update(kwargs["json"])
        return _response(200, [_project_row(memory_summary=kwargs["json"]["memory_summary"],
                                            memory_details=kwargs["json"]["memory_details"],
                                            memory_updated_at=kwargs["json"]["memory_updated_at"])])

    postgrest = _FakePostgrest({
        ("GET", "projects"): lambda _kw: _response(200, [_project_row()]),
        ("GET", "conversations"): lambda _kw: _response(200, [{"id": conversation_id, "title": "週記"}]),
        ("GET", "messages"): lambda _kw: _response(200, [
            {"conversation_id": conversation_id, "role": "user", "content": "我搬到師大宿舍了"},
        ]),
        ("PATCH", "projects"): save,
    })
    completion = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(
        {"summary": "師大碩一，住宿舍", "details": ["每晚寫日記", "住師大宿舍"]}, ensure_ascii=False)))])
    model = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=AsyncMock(return_value=completion))))

    app.dependency_overrides[get_current_user] = lambda: "owner-user"
    try:
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "k"}), \
             patch.object(projects.httpx, "AsyncClient", postgrest), \
             patch("app.routes.projects.get_chat_client", return_value=model):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                response = await ac.post(f"/api/v1/projects/{PROJECT_ID}/memory/refresh",
                                         headers={"Authorization": "Bearer owner-jwt"})
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 200
    body = response.json()
    assert body["refreshed"] is True
    assert body["memory"]["summary"] == "師大碩一，住宿舍"
    assert saved["memory_details"] == ["每晚寫日記", "住師大宿舍"]
    prompt = model.chat.completions.create.call_args.kwargs["messages"][0]["content"]
    assert "我搬到師大宿舍了" in prompt and "Master's student who journals nightly." in prompt
    assert all(call["headers"]["Authorization"] == "Bearer owner-jwt" for call in postgrest.calls)
    assert [(call["method"], call["url"].rsplit("/", 1)[-1]) for call in postgrest.calls] == [
        ("GET", "projects"), ("GET", "conversations"), ("GET", "messages"), ("PATCH", "projects"),
    ]
