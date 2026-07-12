from unittest.mock import AsyncMock

import pytest

from backend.policies import MemoryDecision, MemoryScope
from backend.tools import MemoryQueryTool


@pytest.mark.asyncio
async def test_memory_query_tool_rejects_policy_denial_before_storage_access():
    cold = AsyncMock()
    working = AsyncMock()
    tool = MemoryQueryTool(cold, working)
    decision = MemoryDecision(MemoryScope.DENY_MEMORY, False, "SENSITIVE_WITHOUT_CONSENT")

    with pytest.raises(PermissionError, match="SENSITIVE_WITHOUT_CONSENT"):
        await tool.execute(user_id="user-1", query="private", decision=decision, client=None, model="model")
    cold.assert_not_awaited()
    working.assert_not_awaited()


@pytest.mark.asyncio
async def test_memory_query_tool_queries_sources_in_parallel_and_reports_provenance():
    cold = AsyncMock(return_value="cold memory")
    working = AsyncMock(return_value="working memory")
    tool = MemoryQueryTool(cold, working)
    decision = MemoryDecision(MemoryScope.ALLOW_AGENT_QUERY, True, "SUBSTANTIVE_QUERY")

    result = await tool.execute(
        user_id="user-1",
        query="question",
        decision=decision,
        client=None,
        model="model",
    )

    assert result.content == {"cold": "cold memory", "working": "working memory"}
    assert result.provenance == ("cold_memory", "working_memory")
    cold.assert_awaited_once()
    working.assert_awaited_once()


@pytest.mark.asyncio
async def test_memory_query_tool_bounds_returned_content():
    tool = MemoryQueryTool(
        AsyncMock(return_value="a" * 10),
        AsyncMock(return_value="b" * 10),
        max_content_chars=12,
    )
    decision = MemoryDecision(MemoryScope.ALLOW_AGENT_QUERY, True, "SUBSTANTIVE_QUERY")
    result = await tool.execute(
        user_id="user-1", query="question", decision=decision, client=None, model="model"
    )

    assert result.truncated is True
    assert len(result.content["cold"] + result.content["working"]) == 12
