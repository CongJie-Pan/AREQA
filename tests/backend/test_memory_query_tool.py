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
async def test_memory_query_tool_reports_privacy_safe_substep_trace():
    cold = AsyncMock(return_value="cold memory")
    working = AsyncMock(return_value="working memory")
    tool = MemoryQueryTool(cold, working)
    decision = MemoryDecision(MemoryScope.ALLOW_AGENT_QUERY, True, "EXPLICIT_RECALL_REQUEST")

    result = await tool.execute(
        user_id="user-1",
        query="你還記得我的偏好嗎？",
        decision=decision,
        client=None,
        model="model",
    )

    summary = result.metadata["memory_retrieval"]
    step_names = {step["name"] for step in summary["steps"]}
    assert {"cold_memory", "working_memory"} <= step_names
    assert summary["outcome"] == "retrieved"
    assert summary["result_count_bucket"] == "2-3"
    assert "你還記得" not in str(summary)
    assert "cold memory" not in str(summary)


@pytest.mark.asyncio
async def test_memory_query_tool_suppresses_memory_when_cold_embedding_falls_back():
    async def cold_query(user_id, query, *, top_k, client, model, memory_trace):
        memory_trace.record_step("cold_memory_embedding", 1501, outcome="timeout")
        return "late cold memory"

    working = AsyncMock(return_value="working memory")
    tool = MemoryQueryTool(cold_query, working)
    decision = MemoryDecision(MemoryScope.ALLOW_AGENT_QUERY, True, "SUBSTANTIVE_QUERY")

    result = await tool.execute(
        user_id="user-1",
        query="question",
        decision=decision,
        client=None,
        model="model",
    )

    assert result.content == {"cold": "", "working": "", "_status": "fallback"}
    assert result.metadata["memory_retrieval"]["outcome"] == "fallback"
    assert result.metadata["memory_retrieval"]["result_count_bucket"] == "0"


@pytest.mark.asyncio
async def test_memory_query_tool_keeps_legacy_cold_query_signature_compatible():
    async def cold_query(user_id, query, *, top_k, client, model):
        return "cold memory"

    working = AsyncMock(return_value="")
    tool = MemoryQueryTool(cold_query, working)
    decision = MemoryDecision(MemoryScope.ALLOW_AGENT_QUERY, True, "EXPLICIT_RECALL_REQUEST")

    result = await tool.execute(
        user_id="user-1",
        query="question",
        decision=decision,
        client=None,
        model="model",
    )

    assert result.content["cold"] == "cold memory"
    assert result.metadata["memory_retrieval"]["outcome"] == "retrieved"


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
