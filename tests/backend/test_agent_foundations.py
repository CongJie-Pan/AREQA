import pytest
from unittest.mock import AsyncMock, MagicMock

from backend.agents import TutorAgent
from backend.core import (
    ConversationRuntime,
    SearchMode,
    ToolBudget,
    ToolBudgetExceeded,
    ToolBudgetTracker,
)
from backend.policies import SearchPolicy, SearchReason
from backend.tools import ToolDefinition, ToolRegistry, ToolResult


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("請解釋 dependency injection", False),
        ("今天台北天氣如何", True),
        ("React 最新版本是什麼", True),
        ("Who is the current president?", True),
        ("請問 夏目漱石有寫過哪些書 ?", True),
        ("列出村上春樹的代表作品", True),
    ],
)
def test_auto_search_policy_routes_current_information(query, expected):
    decision = SearchPolicy().evaluate(query, SearchMode.AUTO)
    assert decision.should_search is expected


def test_never_search_policy_cannot_be_overridden_by_current_query():
    decision = SearchPolicy().evaluate("今天最新新聞", SearchMode.NEVER)
    assert decision.should_search is False
    assert decision.reason == SearchReason.USER_DISABLED


@pytest.mark.asyncio
async def test_tutor_shadow_decision_does_not_execute_tools():
    session = ConversationRuntime().start_session(
        user_id="user-1",
        conversation_id="conversation-1",
        request_id=None,
        search_mode=SearchMode.NEVER,
    )
    record = await TutorAgent().evaluate_search_shadow(
        "今天最新新聞",
        session.context,
        evaluation_mode=SearchMode.AUTO,
    )

    assert record.decision.should_search is True
    assert record.decision.reason == SearchReason.CURRENT_INFORMATION_REQUIRED


@pytest.mark.asyncio
async def test_tool_registry_enforces_external_call_budget():
    calls = 0

    async def handler(arguments):
        nonlocal calls
        calls += 1
        return ToolResult("web_search", "ok", arguments, latency_ms=1)

    registry = ToolRegistry()
    registry.register(ToolDefinition("web_search", True, handler))
    budget = ToolBudgetTracker(ToolBudget(max_external_calls=1))

    await registry.execute("web_search", {"query": "first"}, budget)
    with pytest.raises(ToolBudgetExceeded, match="external call"):
        await registry.execute("web_search", {"query": "second"}, budget)
    assert calls == 1


def test_tool_budget_rejects_negative_limits():
    with pytest.raises(ValueError, match="max_tool_calls_per_run"):
        ToolBudget(max_tool_calls_per_run=-1)


@pytest.mark.asyncio
async def test_tutor_agent_uses_bounded_model_decision_for_auto_mode():
    session = ConversationRuntime().start_session(
        user_id="user-1",
        conversation_id="conversation-1",
        request_id=None,
        search_mode=SearchMode.AUTO,
    )
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = (
        '{"should_search": true, "reason_code": "CURRENT_INFORMATION_REQUIRED"}'
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)

    decision = await TutorAgent().decide_search(
        "ambiguous query", session.context, client=client, model="router-model"
    )

    assert decision.should_search is True
    assert decision.reason == SearchReason.CURRENT_INFORMATION_REQUIRED
    assert client.chat.completions.create.await_args.kwargs["max_tokens"] == 80


@pytest.mark.asyncio
async def test_tutor_agent_never_mode_bypasses_model():
    session = ConversationRuntime().start_session(
        user_id="user-1",
        conversation_id="conversation-1",
        request_id=None,
        search_mode=SearchMode.NEVER,
    )
    client = MagicMock()
    client.chat.completions.create = AsyncMock()

    decision = await TutorAgent().decide_search(
        "今天最新新聞", session.context, client=client, model="router-model"
    )

    assert decision.should_search is False
    client.chat.completions.create.assert_not_awaited()


@pytest.mark.asyncio
async def test_tutor_agent_invalid_model_output_falls_back_to_policy():
    session = ConversationRuntime().start_session(
        user_id="user-1",
        conversation_id="conversation-1",
        request_id=None,
        search_mode=SearchMode.AUTO,
    )
    response = MagicMock()
    response.choices = [MagicMock()]
    response.choices[0].message.content = "not-json"
    client = MagicMock()
    client.chat.completions.create = AsyncMock(return_value=response)

    decision = await TutorAgent().decide_search(
        "React 最新版本", session.context, client=client, model="router-model"
    )
    assert decision.should_search is True
    assert decision.reason == SearchReason.CURRENT_INFORMATION_REQUIRED


def test_agent_search_routing_is_enabled_by_default():
    from backend.config import Settings

    settings = Settings()

    assert settings.enable_agent_search_routing is True
    assert settings.agent_search_rollout_percentage == 100.0
