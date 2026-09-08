from unittest.mock import AsyncMock
from types import SimpleNamespace
import logging
import asyncio

import pytest

from backend.services.conversation_context_service import ConversationContextService, _example_instruction
from backend.services.parts_context_service import PartsContext
from backend.services.query_policy_service import (
    AnswerDepth,
    EvidenceMode,
    FollowupMode,
    LearningTechnique,
    ResponsePolicy,
    ResponseStructure,
    ResponseTone,
    TaskIntent,
    VisualSupport,
)
from backend.services.answer_style_service import evidence_mode_overlays, learning_technique_overlays
from services.explicit_memory_cache import explicit_memory_cache


def test_visual_slot_instruction_uses_areqa_image_slot(monkeypatch):
    """Visual prompt should request AREQA-owned XML-like image slot tags."""

    import config as runtime_config

    monkeypatch.setattr(runtime_config.settings, "enable_visual_preflight", False)
    instruction = ConversationContextService._visual_slot_instruction(
        ResponsePolicy(
            task_intent=TaskIntent.EXPLAIN_TEXT,
            answer_depth=AnswerDepth.SCAFFOLDED,
            tone=ResponseTone.TUTORING,
            structure=ResponseStructure.STEP_BY_STEP,
            followup_mode=FollowupMode.OPTIONAL,
            visual_support=VisualSupport.OPTIONAL,
            legacy_policy="NORMAL",
        ),
        "請給我圖解",
    )

    assert "<AREQA_IMAGE_SLOT" in instruction
    assert 'alt="short accessible image description"' in instruction
    assert 'caption="這張圖要幫助使用者理解的重點"' in instruction
    assert 'query="short concrete image search query"' in instruction
    assert "靜默省略" in instruction
    assert "[[AREQA_IMAGE_REQUEST" not in instruction


def test_visual_slot_instruction_requires_policy_or_explicit_visual(monkeypatch):
    """Explanation intent alone must not bypass the agent visual-support gate."""

    import config as runtime_config

    monkeypatch.setattr(runtime_config.settings, "enable_visual_preflight", False)
    instruction = ConversationContextService._visual_slot_instruction(
        ResponsePolicy(
            task_intent=TaskIntent.EXPLAIN_TEXT,
            answer_depth=AnswerDepth.SCAFFOLDED,
            tone=ResponseTone.TUTORING,
            structure=ResponseStructure.STEP_BY_STEP,
            followup_mode=FollowupMode.OPTIONAL,
            legacy_policy="NORMAL",
        ),
        "請解釋這段文字",
    )

    assert instruction == ""


def test_response_policy_instruction_includes_learning_and_evidence_overlays():
    """Final prompt strategy should include selected learning and evidence constraints."""

    instruction = ConversationContextService._response_policy_instruction(
        ResponsePolicy(
            task_intent=TaskIntent.GENERAL_QA,
            answer_depth=AnswerDepth.SCAFFOLDED,
            tone=ResponseTone.TUTORING,
            structure=ResponseStructure.STEP_BY_STEP,
            followup_mode=FollowupMode.OPTIONAL,
            learning_technique=LearningTechnique.TWENTY_HOUR_PLAN,
            evidence_mode=EvidenceMode.MULTI_SOURCE_REQUIRED,
            legacy_policy="NORMAL",
        ),
        {},
        learning_technique_overlays(),
        evidence_mode_overlays(),
    )

    assert "learning_technique: TWENTY_HOUR_PLAN" in instruction
    assert "拆成 10 次" in instruction
    assert "evidence_mode: MULTI_SOURCE_REQUIRED" in instruction
    assert "至少兩個權威來源" in instruction


@pytest.mark.asyncio
async def test_context_prompt_forbids_unsupported_learner_state_claims():
    """The final prompt must not let a disclosure become a learner-state fact."""
    memory_policy = AsyncMock()
    memory_policy.evaluate = lambda _: SimpleNamespace(allow_long_term_query=False)
    service = ConversationContextService(memory_policy=memory_policy, memory_query_tool=AsyncMock())
    snapshot_loader = AsyncMock(return_value="")

    result = await service.build_conversation_context(
        user_id="user-1",
        conversation_id="conversation-1",
        messages=[{"role": "user", "content": "我以前物理不及格，很焦慮"}],
        use_rag=False,
        use_web_search=False,
        force_think=False,
        context_results_obj=None,
        last_user_msg="我以前物理不及格，很焦慮",
        context_prompt="",
        client=None,
        snapshot_loader=snapshot_loader,
        store=None,
        chat_avatar_key="chat_avatar:conversation-1",
    )

    system_prompt = result.messages[0]["content"]
    assert "不得聲稱使用者已理解、掌握或熟悉" in system_prompt
    assert "不得將其改寫成你對使用者能力、情緒、人格或學習進度的判定" in system_prompt


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("interface_language", "user_message", "expected_language"),
    [
        ("en", "請解釋貝氏定理", "繁體中文"),
        ("zh-CN", "請解釋貝氏定理", "繁體中文"),
        ("zh-TW", "請解釋貝氏定理", "繁體中文"),
        ("zh-TW", "Explain Bayes theorem with a simple example", "繁體中文"),
        ("zh-TW", "What is AI?", "繁體中文"),
        ("en", "请解释贝叶斯定理", "簡體中文"),
        ("en", "請用繁體中文解釋 Bayes theorem", "繁體中文"),
        ("zh-TW", "Please answer in English: explain Bayes theorem", "English"),
        ("zh-TW", "請分析這段 prompt:\n```text\nExplain retrieval augmented generation.\n```", "繁體中文"),
    ],
)
async def test_context_prompt_resolves_answer_language(interface_language, user_message, expected_language):
    memory_policy = AsyncMock()
    memory_policy.evaluate = lambda _: SimpleNamespace(allow_long_term_query=False)
    service = ConversationContextService(memory_policy=memory_policy, memory_query_tool=AsyncMock())

    result = await service.build_conversation_context(
        user_id="user-1",
        conversation_id="conversation-1",
        messages=[{"role": "user", "content": user_message}],
        use_rag=False,
        use_web_search=False,
        force_think=False,
        context_results_obj=None,
        last_user_msg=user_message,
        context_prompt="",
        client=None,
        snapshot_loader=AsyncMock(return_value=""),
        store=None,
        chat_avatar_key="chat_avatar:conversation-1",
        interface_language=interface_language,
    )

    system_prompt = result.messages[0]["content"]
    assert f"本回合正式回答必須使用{expected_language}" in system_prompt
    assert "請一律使用繁體中文" not in system_prompt


@pytest.mark.parametrize(
    ("interface_language", "user_message", "expected_instruction"),
    [
        ("zh-TW", "請解釋什麼是貝氏定理", "【案例說明要求】"),
        ("zh-CN", "请解释什么是贝叶斯定理", "【案例说明要求】"),
        ("en", "Explain Bayes theorem", "【Example requirement】"),
    ],
)
def test_example_instruction_matches_resolved_answer_language(
    interface_language,
    user_message,
    expected_instruction,
):
    instruction = _example_instruction(interface_language, user_message)

    assert expected_instruction in instruction
    assert "至少" in instruction or "at least one" in instruction


@pytest.mark.asyncio
async def test_context_plan_can_skip_foreground_long_term_memory(caplog):
    caplog.set_level(logging.INFO)
    memory_policy = AsyncMock()
    memory_policy.evaluate = lambda _: SimpleNamespace(
        allow_long_term_query=True,
        reason_code="SUBSTANTIVE_QUERY",
    )
    memory_query_tool = AsyncMock()
    service = ConversationContextService(
        memory_policy=memory_policy,
        memory_query_tool=memory_query_tool,
    )

    await service.build_conversation_context(
        user_id="user-1",
        conversation_id="conversation-1",
        messages=[{"role": "user", "content": "請解釋 dependency injection"}],
        use_rag=False,
        use_web_search=False,
        force_think=False,
        context_results_obj=None,
        last_user_msg="請解釋 dependency injection",
        context_prompt="",
        client=None,
        snapshot_loader=AsyncMock(return_value=""),
        store=None,
        chat_avatar_key="chat_avatar:conversation-1",
        allow_long_term_memory_query=False,
        memory_skip_reason="LEARNING_HELP",
    )

    memory_query_tool.execute.assert_not_awaited()
    assert "orchestration.long_term_memory_skipped" in caplog.text


@pytest.mark.asyncio
async def test_context_plan_allows_explicit_long_term_memory():
    memory_policy = AsyncMock()
    memory_policy.evaluate = lambda _: SimpleNamespace(
        allow_long_term_query=True,
        reason_code="EXPLICIT_RECALL_REQUEST",
    )
    memory_query_tool = AsyncMock()
    memory_query_tool.execute.return_value.content = {
        "cold": "remembered preference",
        "working": "",
    }
    service = ConversationContextService(
        memory_policy=memory_policy,
        memory_query_tool=memory_query_tool,
    )

    result = await service.build_conversation_context(
        user_id="user-1",
        conversation_id="conversation-1",
        messages=[{"role": "user", "content": "你還記得我的偏好嗎？"}],
        use_rag=False,
        use_web_search=False,
        force_think=False,
        context_results_obj=None,
        last_user_msg="你還記得我的偏好嗎？",
        context_prompt="",
        client=None,
        snapshot_loader=AsyncMock(return_value=""),
        store=None,
        chat_avatar_key="chat_avatar:conversation-1",
        allow_long_term_memory_query=True,
        memory_skip_reason="EXPLICIT_RECALL_REQUEST",
    )

    memory_query_tool.execute.assert_awaited_once()
    assert result.retrieved_memory is True
    assert "remembered preference" in result.messages[0]["content"]


@pytest.mark.asyncio
async def test_explicit_recall_memory_timeout_falls_back_without_retrieved_memory(caplog):
    caplog.set_level(logging.INFO)
    memory_policy = AsyncMock()
    memory_policy.evaluate = lambda _: SimpleNamespace(
        allow_long_term_query=True,
        reason_code="EXPLICIT_RECALL_REQUEST",
    )
    memory_query_tool = AsyncMock()

    async def slow_memory(**kwargs):
        await asyncio.sleep(0.05)
        return SimpleNamespace(content={"cold": "late memory", "working": ""})

    memory_query_tool.execute.side_effect = slow_memory
    service = ConversationContextService(
        memory_policy=memory_policy,
        memory_query_tool=memory_query_tool,
    )

    result = await service.build_conversation_context(
        user_id="user-1",
        conversation_id="conversation-timeout",
        messages=[{"role": "user", "content": "你還記得我的偏好嗎？"}],
        use_rag=False,
        use_web_search=False,
        force_think=False,
        context_results_obj=None,
        last_user_msg="你還記得我的偏好嗎？",
        context_prompt="",
        client=None,
        snapshot_loader=AsyncMock(return_value=""),
        store=None,
        chat_avatar_key="chat_avatar:conversation-timeout",
        allow_long_term_memory_query=True,
        memory_skip_reason="EXPLICIT_RECALL_REQUEST",
        explicit_recall_memory_timeout_ms=1,
        enable_explicit_recall_memory_cache=False,
    )

    assert result.retrieved_memory is False
    assert "late memory" not in result.messages[0]["content"]
    assert "長期記憶查詢逾時" in result.messages[0]["content"]
    assert "本回合沒有使用到長期記憶" in result.messages[0]["content"]
    assert "orchestration.long_term_memory_timeout" in caplog.text
    assert "orchestration.long_term_memory_retrieval_summary" in caplog.text
    assert '"outcome": "timeout"' in caplog.text
    assert "你還記得我的偏好嗎" not in caplog.text


@pytest.mark.asyncio
async def test_cold_memory_embedding_fallback_prompts_visible_no_long_term_memory_notice():
    memory_policy = AsyncMock()
    memory_policy.evaluate = lambda _: SimpleNamespace(
        allow_long_term_query=True,
        reason_code="SUBSTANTIVE_QUERY",
    )
    memory_query_tool = AsyncMock()
    memory_query_tool.execute.return_value.content = {
        "cold": "",
        "working": "",
        "_status": "fallback",
    }
    service = ConversationContextService(
        memory_policy=memory_policy,
        memory_query_tool=memory_query_tool,
    )

    result = await service.build_conversation_context(
        user_id="user-1",
        conversation_id="conversation-fallback",
        messages=[{"role": "user", "content": "請解釋牛頓第一運動定律"}],
        use_rag=False,
        use_web_search=False,
        force_think=False,
        context_results_obj=None,
        last_user_msg="請解釋牛頓第一運動定律",
        context_prompt="",
        client=None,
        snapshot_loader=AsyncMock(return_value=""),
        store=None,
        chat_avatar_key="chat_avatar:conversation-fallback",
    )

    system_prompt = result.messages[0]["content"]
    assert result.retrieved_memory is False
    assert "長期記憶查詢已降級" in system_prompt
    assert "本回合沒有使用到長期記憶" in system_prompt
    assert "<retrieved_memory>" not in system_prompt


@pytest.mark.asyncio
async def test_explicit_recall_memory_cache_hit_avoids_second_query():
    explicit_memory_cache.clear()
    memory_policy = AsyncMock()
    memory_policy.evaluate = lambda _: SimpleNamespace(
        allow_long_term_query=True,
        reason_code="EXPLICIT_RECALL_REQUEST",
    )
    memory_query_tool = AsyncMock()
    memory_query_tool.execute.return_value.content = {
        "cold": "cached preference",
        "working": "",
    }
    service = ConversationContextService(
        memory_policy=memory_policy,
        memory_query_tool=memory_query_tool,
    )
    kwargs = dict(
        user_id="user-1",
        conversation_id="conversation-cache",
        messages=[{"role": "user", "content": "你還記得我的偏好嗎？"}],
        use_rag=False,
        use_web_search=False,
        force_think=False,
        context_results_obj=None,
        last_user_msg="你還記得我的偏好嗎？",
        context_prompt="",
        client=None,
        snapshot_loader=AsyncMock(return_value=""),
        store=None,
        chat_avatar_key="chat_avatar:conversation-cache",
        allow_long_term_memory_query=True,
        memory_skip_reason="EXPLICIT_RECALL_REQUEST",
        explicit_recall_memory_timeout_ms=1000,
        enable_explicit_recall_memory_cache=True,
        explicit_recall_memory_cache_ttl_seconds=120,
    )

    first = await service.build_conversation_context(**kwargs)
    second = await service.build_conversation_context(**kwargs)

    memory_query_tool.execute.assert_awaited_once()
    assert first.retrieved_memory is True
    assert second.retrieved_memory is True
    assert "cached preference" in second.messages[0]["content"]
    explicit_memory_cache.clear()


def test_explicit_recall_memory_cache_key_does_not_include_raw_query():
    key = explicit_memory_cache.make_key(
        user_id="user-1",
        conversation_id="conversation-cache",
        query="你還記得我的偏好嗎？",
    )

    assert key.startswith("explicit-memory:")
    assert "你還記得" not in key
    assert "user-1" not in key
    assert "conversation-cache" not in key


@pytest.mark.asyncio
async def test_recent_reading_question_allows_cross_conversation_hot_focus():
    memory_policy = AsyncMock()
    memory_policy.evaluate = lambda _: SimpleNamespace(
        allow_long_term_query=True,
        reason_code="SUBSTANTIVE_QUERY",
    )
    memory_query_tool = AsyncMock()

    async def snapshot_loader(*args, **kwargs):
        if kwargs.get("include_cross_conversation_focus"):
            return "【工作記憶 (Working Memory)】\n- Current focus: 我最近在讀夏目漱石的《三四郎》，目前讀到第四章。"
        return ""

    service = ConversationContextService(
        memory_policy=memory_policy,
        memory_query_tool=memory_query_tool,
    )

    result = await service.build_conversation_context(
        user_id="user-1",
        conversation_id="conversation-b",
        messages=[{"role": "user", "content": "我最近想讀村上春樹的遇見100%的女孩，和我最近讀的書有哪些共通處？"}],
        use_rag=False,
        use_web_search=False,
        force_think=False,
        context_results_obj=None,
        last_user_msg="我最近想讀村上春樹的遇見100%的女孩，和我最近讀的書有哪些共通處？",
        context_prompt="",
        client=None,
        snapshot_loader=snapshot_loader,
        store=None,
        chat_avatar_key="chat_avatar:conversation-b",
        allow_long_term_memory_query=False,
        memory_skip_reason="GENERAL_CHAT",
    )

    memory_query_tool.execute.assert_not_awaited()
    assert "三四郎" in result.messages[0]["content"]


@pytest.mark.asyncio
async def test_sensitive_recent_question_keeps_cross_conversation_hot_focus_closed():
    memory_policy = AsyncMock()
    memory_policy.evaluate = lambda _: SimpleNamespace(
        allow_long_term_query=True,
        reason_code="SUBSTANTIVE_QUERY",
    )
    memory_query_tool = AsyncMock()
    snapshot_loader = AsyncMock(return_value="")
    service = ConversationContextService(
        memory_policy=memory_policy,
        memory_query_tool=memory_query_tool,
    )

    await service.build_conversation_context(
        user_id="user-1",
        conversation_id="conversation-b",
        messages=[{"role": "user", "content": "我最近家庭壓力和焦慮的事情，跟我之前讀的內容有關嗎？"}],
        use_rag=False,
        use_web_search=False,
        force_think=False,
        context_results_obj=None,
        last_user_msg="我最近家庭壓力和焦慮的事情，跟我之前讀的內容有關嗎？",
        context_prompt="",
        client=None,
        snapshot_loader=snapshot_loader,
        store=None,
        chat_avatar_key="chat_avatar:conversation-b",
        allow_long_term_memory_query=False,
        memory_skip_reason="SENSITIVE_NO_RECALL",
    )

    memory_query_tool.execute.assert_not_awaited()
    assert snapshot_loader.await_args.kwargs["include_cross_conversation_focus"] is False


@pytest.mark.asyncio
async def test_direct_response_policy_adds_answer_first_constraints():
    """DIRECT policy should suppress broad analytical expansion."""

    memory_policy = AsyncMock()
    memory_policy.evaluate = lambda _: SimpleNamespace(allow_long_term_query=False)
    service = ConversationContextService(memory_policy=memory_policy, memory_query_tool=AsyncMock())

    result = await service.build_conversation_context(
        user_id="user-1",
        conversation_id="conversation-direct",
        messages=[{"role": "user", "content": "但是只能選一個"}],
        use_rag=False,
        use_web_search=False,
        force_think=False,
        context_results_obj=None,
        last_user_msg="但是只能選一個",
        context_prompt="",
        client=None,
        snapshot_loader=AsyncMock(return_value=""),
        store=None,
        chat_avatar_key="chat_avatar:conversation-direct",
        response_policy=ResponsePolicy(
            task_intent=TaskIntent.ANSWER_EXAM,
            answer_depth=AnswerDepth.DIRECT,
            tone=ResponseTone.PLAIN,
            structure=ResponseStructure.SHORT,
            followup_mode=FollowupMode.NONE,
            legacy_policy="NORMAL",
        ),
    )

    system_prompt = result.messages[0]["content"]
    assert "task_intent: ANSWER_EXAM" in system_prompt
    assert "先給答案，再給簡短判斷理由" in system_prompt
    assert "深度控制：DIRECT" in system_prompt
    assert "結尾不要加引導問題" in system_prompt
    assert "過度深度防護" in system_prompt


@pytest.mark.asyncio
async def test_scaffolded_response_policy_adds_plain_step_constraints():
    """SCAFFOLDED policy should keep explanations local and plain."""

    memory_policy = AsyncMock()
    memory_policy.evaluate = lambda _: SimpleNamespace(allow_long_term_query=False)
    service = ConversationContextService(memory_policy=memory_policy, memory_query_tool=AsyncMock())

    result = await service.build_conversation_context(
        user_id="user-1",
        conversation_id="conversation-scaffold",
        messages=[{"role": "user", "content": "我聽不懂，可以白話些嗎"}],
        use_rag=False,
        use_web_search=False,
        force_think=False,
        context_results_obj=None,
        last_user_msg="我聽不懂，可以白話些嗎",
        context_prompt="",
        client=None,
        snapshot_loader=AsyncMock(return_value=""),
        store=None,
        chat_avatar_key="chat_avatar:conversation-scaffold",
        response_policy=ResponsePolicy(
            task_intent=TaskIntent.EXPLAIN_TEXT,
            answer_depth=AnswerDepth.SCAFFOLDED,
            tone=ResponseTone.PLAIN,
            structure=ResponseStructure.STEP_BY_STEP,
            followup_mode=FollowupMode.OPTIONAL,
            legacy_policy="NORMAL",
        ),
    )

    system_prompt = result.messages[0]["content"]
    assert "task_intent: EXPLAIN_TEXT" in system_prompt
    assert "深度控制：SCAFFOLDED" in system_prompt
    assert "語氣控制：PLAIN" in system_prompt
    assert "不要上升到宏大框架" in system_prompt
    assert "profile: AREQA_TEACHING_V1" in system_prompt
    assert "先講白話直覺" in system_prompt
    assert "過度深度防護" in system_prompt


@pytest.mark.asyncio
async def test_parts_context_is_injected_after_response_policy():
    """PARTS context should be available to the main model each turn."""

    memory_policy = AsyncMock()
    memory_policy.evaluate = lambda _: SimpleNamespace(allow_long_term_query=False)
    service = ConversationContextService(memory_policy=memory_policy, memory_query_tool=AsyncMock())

    result = await service.build_conversation_context(
        user_id="user-1",
        conversation_id="conversation-parts",
        messages=[{"role": "user", "content": "我算這題對嗎？"}],
        use_rag=False,
        use_web_search=False,
        force_think=False,
        context_results_obj=None,
        last_user_msg="我算這題對嗎？",
        context_prompt="",
        client=None,
        snapshot_loader=AsyncMock(return_value=""),
        store=None,
        chat_avatar_key="chat_avatar:conversation-parts",
        response_policy=ResponsePolicy(
            task_intent=TaskIntent.EXPLAIN_TEXT,
            answer_depth=AnswerDepth.SCAFFOLDED,
            tone=ResponseTone.TUTORING,
            structure=ResponseStructure.STEP_BY_STEP,
            followup_mode=FollowupMode.OPTIONAL,
            legacy_policy="NORMAL",
        ),
        parts_context=PartsContext(
            persona="引導型數學理解教練",
            act="檢查解題步驟並指出可能錯誤",
            recipient="程度未知的學習者，不假設已掌握概念",
            theme="運算順序與代數式計算",
            structure="短回答 + 分步檢查 + 最多一個診斷性追問",
            composed_instruction="你現在的角色是「引導型數學理解教練」。請檢查解題步驟並指出可能錯誤。",
            confidence="high",
            missing_fields=("recipient_level",),
        ),
    )

    system_prompt = result.messages[0]["content"]
    assert "【本回合回答策略】" in system_prompt
    assert "【PARTS 任務上下文】" in system_prompt
    assert "P: 引導型數學理解教練" in system_prompt
    assert "T: 運算順序與代數式計算" in system_prompt
    assert "【由 PARTS 生成的本回合任務指令】" in system_prompt
    assert "請遵循「本回合任務指令」回答，但不要輸出 P/A/R/T/S 標籤" in system_prompt
    assert "請檢查解題步驟並指出可能錯誤" in system_prompt
    assert "不得覆蓋文獻引用" in system_prompt


@pytest.mark.asyncio
async def test_rag_rules_remain_above_parts_context():
    """PARTS must not weaken RAG citation and untrusted-context boundaries."""

    memory_policy = AsyncMock()
    memory_policy.evaluate = lambda _: SimpleNamespace(allow_long_term_query=False)
    service = ConversationContextService(memory_policy=memory_policy, memory_query_tool=AsyncMock())

    result = await service.build_conversation_context(
        user_id="user-1",
        conversation_id="conversation-rag-parts",
        messages=[{"role": "user", "content": "根據資料解釋"}],
        use_rag=True,
        use_web_search=False,
        force_think=False,
        context_results_obj={"status": "ok"},
        last_user_msg="根據資料解釋",
        context_prompt="[文獻1] 測試資料\n內容: 測試。",
        client=None,
        snapshot_loader=AsyncMock(return_value=""),
        store=None,
        chat_avatar_key="chat_avatar:conversation-rag-parts",
        parts_context=PartsContext(
            persona="資料導讀教練",
            act="根據提供的參考資料回答並維持引用格式",
            recipient="程度未知的學習者，不假設已掌握概念",
            theme="資料中的核心概念",
            structure="分步解釋 + 引用文獻",
            composed_instruction="你現在的角色是「資料導讀教練」。請根據提供的參考資料回答並維持引用格式。",
            confidence="high",
            missing_fields=(),
        ),
    )

    system_prompt = result.messages[0]["content"]
    assert "已注入 <context> 參考資料，請嚴格依文獻回答並標註來源" in system_prompt
    assert "外部資料安全邊界" in system_prompt
    assert "【PARTS 優先權邊界】" in system_prompt
    assert "不得覆蓋文獻引用" in system_prompt


@pytest.mark.asyncio
async def test_deep_dive_response_policy_enables_reflective_overlay():
    """DEEP_DIVE policy should preserve AREQA's reflective strength on demand."""

    memory_policy = AsyncMock()
    memory_policy.evaluate = lambda _: SimpleNamespace(allow_long_term_query=False)
    service = ConversationContextService(memory_policy=memory_policy, memory_query_tool=AsyncMock())

    result = await service.build_conversation_context(
        user_id="user-1",
        conversation_id="conversation-deep",
        messages=[{"role": "user", "content": "為什麼戰爭會使人喪失人性？"}],
        use_rag=False,
        use_web_search=False,
        force_think=False,
        context_results_obj=None,
        last_user_msg="為什麼戰爭會使人喪失人性？",
        context_prompt="",
        client=None,
        snapshot_loader=AsyncMock(return_value=""),
        store=None,
        chat_avatar_key="chat_avatar:conversation-deep",
        response_policy=ResponsePolicy(
            task_intent=TaskIntent.DISCUSS_IDEA,
            answer_depth=AnswerDepth.DEEP_DIVE,
            tone=ResponseTone.ANALYTICAL,
            structure=ResponseStructure.ARGUMENT,
            followup_mode=FollowupMode.OPTIONAL,
            legacy_policy="PUSH_LIMIT",
        ),
    )

    system_prompt = result.messages[0]["content"]
    assert "task_intent: DISCUSS_IDEA" in system_prompt
    assert "深度控制：DEEP_DIVE" in system_prompt
    assert "語氣控制：ANALYTICAL" in system_prompt
    assert "允許展開歷史、哲學、文學或跨領域深度分析" in system_prompt
    assert "過度深度防護" not in system_prompt
