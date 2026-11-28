"""Teaching Layer contract: pure rendering, section order, and medium adaptation."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

import config as runtime_config
from services.conversation.context import ConversationContextService
from services.conversation.research_coach import render_research_coach_prompt
from services.query_policy.classifier import default_response_policy
from services.teaching import prompts
from services.teaching.engine import (
    TeachingMaterials,
    TeachingRequest,
    apply_response_mode,
    render_system_prompt,
)

POLICY_MARKER = "任務是一般問答"


@pytest.fixture(autouse=True)
def _stable_settings(monkeypatch):
    monkeypatch.setattr(runtime_config.settings, "enable_visual_preflight", False)
    monkeypatch.setattr(runtime_config.settings, "enable_parts_prompt_context", True)


def test_render_needs_only_data_and_is_deterministic():
    request = TeachingRequest(last_user_msg="請解釋貝氏定理")

    first = render_system_prompt(request)

    assert first == render_system_prompt(request)
    assert first.startswith(prompts.SYSTEM_PROMPT_NORMAL)
    assert POLICY_MARKER in first


@pytest.mark.parametrize(
    ("grounded", "force_think", "base"),
    [
        (False, False, prompts.SYSTEM_PROMPT_NORMAL),
        (False, True, prompts.SYSTEM_PROMPT_FORCE_THINK),
        (True, False, prompts.SYSTEM_PROMPT_WITH_RAG),
        (True, True, prompts.SYSTEM_PROMPT_WITH_RAG_THINK),
    ],
)
def test_base_prompt_follows_grounding_and_reasoning(grounded, force_think, base):
    prompt = render_system_prompt(TeachingRequest(last_user_msg="hi", grounded=grounded, force_think=force_think))

    assert prompt.startswith(base)
    assert ("已注入 <context>" in prompt) is grounded
    assert ("禁止輸出【文獻N】" in prompt) is not grounded


def test_materials_render_in_contract_order():
    prompt = render_system_prompt(
        TeachingRequest(last_user_msg="這不對吧", force_think=True),
        TeachingMaterials(
            working_memory="HOT",
            learner_state="STARTING",
            roleplay_character="蘇格拉底",
            retrieved_memory="COLD",
            working_context="\n\nWORKING",
        ),
    )

    markers = [
        POLICY_MARKER,
        "<working_memory>\nHOT\n</working_memory>",
        "STARTING 階段",
        "扮演「蘇格拉底」",
        "<retrieved_memory>\nCOLD\n</retrieved_memory>",
        "WORKING",
        "思考過程請務必簡明扼要",
        "【自我糾錯機制】",
    ]
    positions = [prompt.index(marker) for marker in markers]
    assert positions == sorted(positions)


def test_absent_learner_state_omits_state_block():
    without_lookup = render_system_prompt(TeachingRequest(last_user_msg="hi"))
    unknown_state = render_system_prompt(TeachingRequest(last_user_msg="hi"), TeachingMaterials(learner_state=""))

    assert "動態表達限制" not in without_lookup
    assert unknown_state == without_lookup


@pytest.mark.parametrize(("status", "marker"), [("timeout", "查詢逾時"), ("fallback", "查詢已降級")])
def test_degraded_long_term_memory_is_disclosed(status, marker):
    prompt = render_system_prompt(TeachingRequest(last_user_msg="hi"), TeachingMaterials(long_term_memory_status=status))

    assert marker in prompt
    assert "本回合沒有使用到長期記憶" in prompt


def test_topic_finder_pins_coach_block_and_card_last():
    prompt = render_system_prompt(
        TeachingRequest(last_user_msg="我想找研究題目", tutor_profile="research_coach", response_policy=default_response_policy()),
        TeachingMaterials(working_memory="HOT", topic_card="\nCARD_END"),
    )

    assert POLICY_MARKER not in prompt
    assert prompt.endswith(render_research_coach_prompt() + "\nCARD_END")


def test_topic_card_is_ignored_outside_topic_finder():
    prompt = render_system_prompt(TeachingRequest(last_user_msg="hi"), TeachingMaterials(topic_card="\nCARD_END"))

    assert "CARD_END" not in prompt


def test_text_mode_returns_messages_untouched():
    messages = [{"role": "system", "content": "SYS"}]

    assert apply_response_mode(messages, "text") is messages


def test_voice_mode_appends_to_system_without_mutating_input():
    messages = [{"role": "system", "content": "SYS"}, {"role": "user", "content": "hi"}]

    voiced = apply_response_mode(messages, "voice")

    assert messages[0]["content"] == "SYS"
    assert voiced[0]["content"].startswith("SYS\n\n【Live Voice 回答格式】")
    assert voiced[1] == messages[1]


def test_voice_mode_adds_system_when_missing():
    voiced = apply_response_mode([{"role": "user", "content": "hi"}], "voice")

    assert voiced[0]["role"] == "system"
    assert voiced[0]["content"].startswith("【Live Voice 回答格式】")


def test_app_prompts_reexports_teaching_constants():
    from app import prompts as app_prompts

    assert app_prompts.SYSTEM_PROMPT_NORMAL is prompts.SYSTEM_PROMPT_NORMAL
    assert app_prompts.RESPONSE_POLICY_OVERLAYS is prompts.RESPONSE_POLICY_OVERLAYS


class _Store:
    async def get_hot_memory(self, user_id):
        return {"current_learner_state": "TINKERING", "chat_avatar:c1": "孔子"}


@pytest.mark.asyncio
async def test_context_service_passes_gathered_materials_to_engine():
    """Integration: the service gathers memory, then the engine alone renders it."""

    memory_policy = SimpleNamespace(evaluate=lambda _: SimpleNamespace(allow_long_term_query=True, reason_code="X"))
    service = ConversationContextService(memory_policy=memory_policy, memory_query_tool=AsyncMock())
    service._query_long_term_memory = AsyncMock(return_value={"cold": "COLD", "working": "\n\nWORKING"})

    result = await service.build_conversation_context(
        user_id="u1", conversation_id="c1", messages=[{"role": "user", "content": "請解釋貝氏定理"}],
        use_rag=False, use_web_search=False, force_think=False, context_results_obj=None,
        last_user_msg="請解釋貝氏定理", context_prompt="", client=None,
        snapshot_loader=AsyncMock(return_value="HOT"), store=_Store(), chat_avatar_key="chat_avatar:c1",
    )

    expected = render_system_prompt(
        TeachingRequest(last_user_msg="請解釋貝氏定理"),
        TeachingMaterials(
            working_memory="HOT", learner_state="TINKERING", roleplay_character="孔子",
            retrieved_memory="COLD", working_context="\n\nWORKING",
        ),
    )
    assert result.messages[0] == {"role": "system", "content": expected}
    assert result.retrieved_memory is True


@pytest.mark.parametrize("profile", ["general", "english", "unknown", None, 3])
def test_ordinary_profiles_keep_default_capabilities(profile):
    from services.teaching.profiles import ProfileCapabilities, capabilities_for

    assert capabilities_for(profile) == ProfileCapabilities()


def test_topic_finder_capabilities_restrict_search_images_and_length():
    from services.conversation.research_coach import TOPIC_FINDER_MAX_TOKENS
    from services.teaching.profiles import capabilities_for

    capabilities = capabilities_for("research_coach")

    assert not capabilities.auto_web_search
    assert not capabilities.image_slots
    assert not capabilities.paper_auto_explain
    assert not capabilities.response_policy_overlay
    assert capabilities.overlay_last
    assert capabilities.max_answer_tokens == TOPIC_FINDER_MAX_TOKENS
