"""Projects regressions: turns outside a project behave exactly as before.

Guards the stream path that every chat takes: no extra Supabase lookup (and so
no extra latency) without a valid project, guests never look projects up,
collaborative isolation still wins, and the assembled prompt is untouched.
"""
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app, get_optional_current_user
from services.conversation.collaboration import CollaborationContext
from services.conversation.projects import ProjectContext, apply_project_prompt
from services.orchestration import answer_preparation
from services.query_policy.models import AttachmentTask

PROJECT_ID = "7a1c2b6e-1d2a-4c3b-9a8e-123456789abc"
CONVERSATION_ID = "3f1c2b6e-1d2a-4c3b-9a8e-123456789abc"


class _CapturingOrchestrator:
    def __init__(self, captured):
        self.captured = captured

    def execute(self, **kwargs):
        self.captured.update(kwargs)

        async def events():
            yield "data: [DONE]\n\n"

        return events()


async def _stream(*, user="owner-user", body=None, collaboration=None, multipart=False):
    captured = {}
    lookup = AsyncMock(return_value=ProjectContext(state="loaded", instructions="project rule"))
    if user:
        app.dependency_overrides[get_optional_current_user] = lambda: user
    else:
        app.dependency_overrides[get_optional_current_user] = lambda: None
    payload = {"conversation_id": CONVERSATION_ID, "messages": [{"role": "user", "content": "hi"}], **(body or {})}
    try:
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "mock"}), \
             patch("services.orchestration_service.OrchestrationService", return_value=_CapturingOrchestrator(captured)), \
             patch("app.routes.stream.load_collaboration_context",
                   new=AsyncMock(return_value=collaboration or CollaborationContext(state="personal"))), \
             patch("app.routes.stream.load_project_context", new=lookup):
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
                if multipart:
                    response = await ac.post("/api/v1/stream", headers={"Authorization": "Bearer jwt"},
                                             files={"messages": (None, json.dumps(payload))})
                else:
                    response = await ac.post("/api/v1/stream", headers={"Authorization": "Bearer jwt"}, json=payload)
    finally:
        app.dependency_overrides.pop(get_optional_current_user, None)
    return response, captured, lookup


@pytest.mark.asyncio
async def test_chat_without_project_makes_no_project_lookup():
    response, captured, lookup = await _stream()
    assert response.status_code == 200
    lookup.assert_not_awaited()
    assert "project_prompt" not in captured and "isolated_context" not in captured


@pytest.mark.asyncio
@pytest.mark.parametrize("project_id", ["", "not-a-uuid", "7a1c2b6e; drop table projects"])
async def test_malformed_project_ids_are_ignored_without_lookup(project_id):
    response, captured, lookup = await _stream(body={"project_id": project_id})
    assert response.status_code == 200
    lookup.assert_not_awaited()
    assert "project_prompt" not in captured


@pytest.mark.asyncio
async def test_guests_never_look_up_projects():
    response, captured, lookup = await _stream(user=None, body={"project_id": PROJECT_ID})
    assert response.status_code == 200
    lookup.assert_not_awaited()
    assert "project_prompt" not in captured


@pytest.mark.asyncio
async def test_collaborative_isolation_still_applies_inside_a_project():
    collaboration = CollaborationContext(state="collaborative", role="editor",
                                         messages=[{"role": "user", "content": "owner q", "message_id": "m1"}])
    response, captured, _lookup = await _stream(body={"project_id": PROJECT_ID}, collaboration=collaboration)
    assert response.status_code == 200
    assert captured["isolated_context"] is True


@pytest.mark.asyncio
async def test_multipart_turns_still_carry_project_id():
    response, captured, lookup = await _stream(body={"project_id": PROJECT_ID}, multipart=True)
    assert response.status_code == 200
    lookup.assert_awaited_once()
    assert lookup.await_args.args[0] == PROJECT_ID
    assert "project rule" in captured["project_prompt"]


class _FakePrepService:
    async def _node_prompt_assembly(self, *args, **kwargs):
        return [{"role": "system", "content": "BASE"}, {"role": "user", "content": "q"}]

    def _attach_to_latest_user_message(self, messages, attachments):
        return messages

    def _add_attachment_grounding_instruction(self, messages):
        return messages

    def _add_missing_visual_attachment_instruction(self, messages, _last):
        return messages, False

    def _add_paper_auto_explain_instruction(self, messages):
        return messages


@pytest.mark.asyncio
async def test_prepare_answer_without_project_prompt_is_unchanged(monkeypatch):
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
        pdf_attachment_count=0, max_tokens=2048,
    )
    assert messages == [{"role": "system", "content": "BASE"}, {"role": "user", "content": "q"}]


def test_empty_overlay_returns_the_same_list_object():
    messages = [{"role": "system", "content": "BASE"}]
    assert apply_project_prompt(messages, "") is messages
