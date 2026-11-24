"""Topic Finder (research_coach) conversation kind: normalization, prompt, and turn limits."""

import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from backend.main import app, get_current_user, get_optional_current_user
from services import prompt_skills
from services.conversation import research_coach
from services.conversation.image_generation import IMAGE_TOOL
from services.conversation.stream_request import tools_for_image_slots
from services.orchestration import answer_preparation
from services.query_policy.models import AttachmentTask


def _document(payload):
    return (
        "# Notes\nDO_NOT_INJECT_THIS_NOTE\n"
        "<!-- AREQA_RUNTIME_PROMPT_BEGIN -->\n```json\n"
        + json.dumps(payload, ensure_ascii=False)
        + "\n```\n<!-- AREQA_RUNTIME_PROMPT_END -->\n"
    )


@pytest.fixture
def skill_root(tmp_path, monkeypatch):
    prompt_skills.load_prompt_skill.cache_clear()
    monkeypatch.setattr(prompt_skills, "_SKILLS_ROOT", tmp_path)
    yield tmp_path
    prompt_skills.load_prompt_skill.cache_clear()


# --- Unit: conversation kind normalization -------------------------------------------------


@pytest.mark.parametrize(("raw", "expected"), [
    ("research_coach", "research_coach"),
    ("  Research_Coach ", "research_coach"),
    ("chat", "chat"),
    ("", "chat"),
    (None, "chat"),
    ("research-coach", "chat"),
    ("english", "chat"),
    (1, "chat"),
    (["research_coach"], "chat"),
])
def test_normalize_conversation_kind_allows_only_known_kinds(raw, expected):
    assert research_coach.normalize_conversation_kind(raw) == expected


def test_resolve_prompt_profile_forces_coach_for_topic_finder():
    assert research_coach.resolve_prompt_profile("english", "research_coach") == "research_coach"
    assert research_coach.resolve_prompt_profile("general", "research_coach") == "research_coach"
    assert research_coach.resolve_prompt_profile("english", "chat") == "english"
    assert research_coach.resolve_prompt_profile("general", "chat") == "general"


# --- Unit: skill loading and rendering ------------------------------------------------------


def test_coach_prompt_uses_payload_rules_without_maintenance_notes(skill_root):
    (skill_root / "research_topic_coach_skill.md").write_text(_document({"rules": ["Coach rule A", "Coach rule B"]}))

    prompt = research_coach.render_prompt_profile("research_coach")

    assert "Workspace：Topic Finder" in prompt
    assert "- Coach rule A" in prompt and "- Coach rule B" in prompt
    assert "不得覆蓋回答語言" in prompt
    assert "DO_NOT_INJECT_THIS_NOTE" not in prompt


@pytest.mark.parametrize("content", [
    b"no runtime block",
    _document({"rules": []}).encode(),
    _document({"rules": "not a list"}).encode(),
    _document({"rules": ["ok"], "extra": "bad"}).encode(),
    _document({"rules": ["ok"]}).replace('"rules": ["ok"]', '"rules": ["a"], "rules": ["b"]').encode(),
    b"x" * (64 * 1024 + 1),
])
def test_invalid_coach_skill_falls_back_to_general_and_logs_safely(skill_root, caplog, content):
    (skill_root / "research_topic_coach_skill.md").write_bytes(content)

    with caplog.at_level(logging.INFO):
        prompt = research_coach.render_prompt_profile("research_coach")

    assert prompt == ""
    messages = " ".join(record.getMessage() for record in caplog.records)
    assert "research_coach.skill_fallback" in messages
    assert "prompt_skill.fallback skill_id=research-topic-coach" in messages
    assert "ok" not in messages and "xxxx" not in messages


def test_missing_coach_skill_falls_back_to_general(skill_root):
    assert research_coach.render_prompt_profile("research_coach") == ""


def test_render_prompt_profile_delegates_non_coach_profiles(skill_root):
    (skill_root / "english_tutor_skill.md").write_text(_document({"rules": ["English rule"]}))

    assert research_coach.render_prompt_profile("general") == ""
    assert "English rule" in research_coach.render_prompt_profile("english")
    assert "Topic Finder" not in research_coach.render_prompt_profile("english")


def test_client_facing_tutor_renderer_never_selects_coach(skill_root):
    from services.conversation.tutor_profile import render_tutor_profile_prompt

    (skill_root / "research_topic_coach_skill.md").write_text(_document({"rules": ["Coach rule"]}))
    assert render_tutor_profile_prompt("research_coach") == ""


def test_shipped_coach_skill_is_valid_and_keeps_core_rules():
    prompt_skills.load_prompt_skill.cache_clear()
    try:
        prompt = research_coach.render_prompt_profile("research_coach")
        assert "RESEARCH_TOPIC_COACH_SKILL_V4" in prompt
        assert "never declare that a candidate has passed a stage" in prompt
        assert "may jump forward or back" in prompt
        assert "Do not claim you have searched" in prompt
        assert "Could this problem be solved by new technology or by events within a few years?" in prompt
        assert "Stage 5 (feasibility)" in prompt and "research ethics" in prompt
        assert "Do not generate images" in prompt
        # V3 reasoning–revision loop: both steers keep the learner in charge.
        assert "【回頭檢查】" in prompt and "if they say it has no effect, accept it" in prompt
        assert "【本輪缺口】" in prompt and "Never present the gap as a score" in prompt
        # V4 answer shape after the 2026-11-24 test run.
        assert "最後且優先的回答規則" in prompt
        assert "reply in 3 to 6 plain sentences" in prompt and "No headings" in prompt
        assert "No praise openings" in prompt and "do not invent cases" in prompt
        assert "Never copy those labels" in prompt
        assert "never say that you moved the learner to another stage" in prompt
        assert "Format: keep turns short" not in prompt
        assert "Runtime prompt payload" not in prompt
    finally:
        prompt_skills.load_prompt_skill.cache_clear()


# --- Unit: image tool removal ---------------------------------------------------------------


def test_tools_for_image_slots_removes_image_tool_only_without_slots():
    letter_tool = {"type": "function", "function": {"name": "send_epistolary_letter"}}
    tools = [IMAGE_TOOL, letter_tool]

    assert tools_for_image_slots(tools, 2) is tools
    assert tools_for_image_slots(tools, 0) == [letter_tool]
    assert tools == [IMAGE_TOOL, letter_tool]


# --- Unit: answer preparation limits --------------------------------------------------------


class _FakeService:
    def __init__(self):
        self.prompt_kwargs = {}
        self.paper_instruction_added = False

    async def _node_prompt_assembly(self, *args, **kwargs):
        self.prompt_kwargs = kwargs
        return [{"role": "system", "content": "base"}, {"role": "user", "content": "q"}]

    def _attach_to_latest_user_message(self, messages, attachments):
        return messages

    def _add_attachment_grounding_instruction(self, messages):
        return messages

    def _add_missing_visual_attachment_instruction(self, messages, _last):
        return messages, False

    def _add_paper_auto_explain_instruction(self, messages):
        self.paper_instruction_added = True
        return messages


async def _prepare(tutor_profile, monkeypatch):
    monkeypatch.setattr(answer_preparation.settings, "enable_visual_preflight", False)
    monkeypatch.setattr(answer_preparation.settings, "enable_pdf_paper_auto_explain", True)
    service = _FakeService()
    policy = SimpleNamespace(
        legacy_policy="DIRECT_ANSWER",
        attachment_task=AttachmentTask.PAPER_AUTO_EXPLAIN,
        attachment_reason=SimpleNamespace(value="test"),
    )
    result = await answer_preparation.prepare_answer(
        service, user_id="u", conversation_id="c", messages=[{"role": "user", "content": "q"}],
        use_rag=False, use_web_search=False, force_think=False, context_results_obj=None,
        last_user_msg="q", run_state=SimpleNamespace(context_prompt=""),
        trace=SimpleNamespace(mark=lambda _name: None), turn_plan=None, turn_plan_enabled=False,
        response_policy=policy, interface_language="zh-TW", tutor_profile=tutor_profile,
        response_mode="text", has_attachments=True, attachments=[], attachment_visual_sources=[],
        pdf_attachment_count=1, max_tokens=2048,
    )
    return service, result


@pytest.mark.asyncio
async def test_topic_finder_turn_has_no_image_slots_and_no_forced_paper_walkthrough(monkeypatch):
    service, (_messages, _tokens, max_image_slots, _blocks) = await _prepare("research_coach", monkeypatch)

    assert max_image_slots == 0
    assert service.paper_instruction_added is False
    assert service.prompt_kwargs["tutor_profile"] == "research_coach"


@pytest.mark.asyncio
async def test_topic_finder_caps_the_answer_token_budget(monkeypatch):
    _service, (_messages, coach_tokens, _slots, _blocks) = await _prepare("research_coach", monkeypatch)
    _service, (_messages, chat_tokens, _slots, _blocks) = await _prepare("general", monkeypatch)

    assert coach_tokens == research_coach.TOPIC_FINDER_MAX_TOKENS
    assert chat_tokens == 2048


@pytest.mark.asyncio
async def test_chat_turn_keeps_paper_walkthrough_and_image_slots(monkeypatch):
    service, (_messages, _tokens, max_image_slots, _blocks) = await _prepare("general", monkeypatch)

    assert max_image_slots == 4
    assert service.paper_instruction_added is True


# --- Integration: context builder -----------------------------------------------------------


async def _system_prompt(tutor_profile):
    from backend.services.conversation_context_service import ConversationContextService

    memory_policy = AsyncMock()
    memory_policy.evaluate = lambda _: SimpleNamespace(allow_long_term_query=False)
    service = ConversationContextService(memory_policy=memory_policy, memory_query_tool=AsyncMock())
    result = await service.build_conversation_context(
        user_id="user-1", conversation_id="conversation-1",
        messages=[{"role": "user", "content": "我想找研究題目"}],
        use_rag=False, use_web_search=False, force_think=False, context_results_obj=None,
        last_user_msg="我想找研究題目", context_prompt="", client=None,
        snapshot_loader=AsyncMock(return_value=""), store=None,
        chat_avatar_key="chat_avatar:conversation-1", tutor_profile=tutor_profile,
    )
    return result.messages[0]["content"]


@pytest.mark.asyncio
async def test_context_includes_coach_skill_only_for_topic_finder():
    prompt_skills.load_prompt_skill.cache_clear()
    try:
        coach_prompt = await _system_prompt("research_coach")
        chat_prompt = await _system_prompt("general")
    finally:
        prompt_skills.load_prompt_skill.cache_clear()

    assert "Workspace：Topic Finder" in coach_prompt
    assert "RESEARCH_TOPIC_COACH_SKILL_V4" in coach_prompt
    assert "本回合正式回答必須使用繁體中文" in coach_prompt
    assert "Topic Finder" not in chat_prompt
    assert "Tutor Profile：English Tutor" not in coach_prompt


# --- Integration: stream route --------------------------------------------------------------


@pytest.fixture
def route_auth():
    app.dependency_overrides[get_current_user] = lambda: "default_user"
    app.dependency_overrides[get_optional_current_user] = lambda: "default_user"
    yield
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_optional_current_user, None)


async def _post_stream(payload):
    captured = {}

    class CapturingOrchestrator:
        def execute(self, **kwargs):
            captured.update(kwargs)

            async def events():
                yield "data: [DONE]\n\n"

            return events()

    with patch.dict("os.environ", {"OPENROUTER_API_KEY": "mock-token"}), \
         patch("services.orchestration_service.OrchestrationService", return_value=CapturingOrchestrator()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post("/api/v1/stream", json=payload)
    return response, captured


@pytest.mark.asyncio
async def test_stream_topic_finder_uses_coach_profile_and_drops_english(route_auth, caplog):
    secret = "我的痛點是這個秘密內容"
    with caplog.at_level(logging.INFO, logger="backend.main"):
        response, captured = await _post_stream({
            "messages": [{"role": "user", "content": secret}],
            "conversation_kind": "research_coach",
            "tutor_profile": "english",
        })

    assert response.status_code == 200
    assert captured["tutor_profile"] == "research_coach"
    accepted = [r.getMessage() for r in caplog.records if "stream.request_accepted" in r.getMessage()]
    assert accepted and "conversation_kind=research_coach" in accepted[0]
    assert "tutor_profile=general" in accepted[0]
    assert all(secret not in record.getMessage() for record in caplog.records)


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", [None, "chat", "unknown", 7])
async def test_stream_without_topic_finder_keeps_existing_profiles(route_auth, kind):
    payload = {"messages": [{"role": "user", "content": "Help with Macbeth"}], "tutor_profile": "english"}
    if kind is not None:
        payload["conversation_kind"] = kind
    response, captured = await _post_stream(payload)

    assert response.status_code == 200
    assert captured["tutor_profile"] == "english"


@pytest.mark.asyncio
async def test_stream_multipart_carries_topic_finder_kind(route_auth):
    captured = {}

    class CapturingOrchestrator:
        def execute(self, **kwargs):
            captured.update(kwargs)

            async def events():
                yield "data: [DONE]\n\n"

            return events()

    payload = {"messages": [{"role": "user", "content": "請看這篇"}], "conversation_kind": "research_coach"}
    with patch.dict("os.environ", {"OPENROUTER_API_KEY": "mock-token"}), \
         patch("services.orchestration_service.OrchestrationService", return_value=CapturingOrchestrator()), \
         patch("services.attachments.parsing.process_attachments", new_callable=AsyncMock, return_value=[]):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/api/v1/stream",
                data={"messages": json.dumps(payload)},
                files={"attachments": ("note.txt", b"hello", "text/plain")},
            )

    assert response.status_code == 200
    assert captured["tutor_profile"] == "research_coach"
