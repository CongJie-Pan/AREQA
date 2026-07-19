from unittest.mock import AsyncMock
from types import SimpleNamespace
import logging

import pytest

from backend.services.conversation_context_service import ConversationContextService


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
