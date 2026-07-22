import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from backend.cold_memory import ColdMemoryRetriever
from backend.services.memory_retrieval_trace import MemoryRetrievalTrace

@pytest.mark.asyncio
async def test_cold_memory_search_pg():
    # Mock engine and session
    mock_cursor_vec = MagicMock()
    mock_cursor_vec.fetchall.return_value = [(1, 0.1), (2, 0.2)]
    
    mock_cursor_bm25 = MagicMock()
    mock_cursor_bm25.fetchall.return_value = [(2, 0.8), (3, 0.9)]
    
    mock_cursor_text = MagicMock()
    mock_cursor_text.fetchone.side_effect = [("Text 2",), ("Text 3",), ("Text 1",)]
    
    mock_session = AsyncMock()
    # Handle the different execute calls based on the SQL text
    async def mock_execute(sql, params=None):
        sql_str = str(sql).lower()
        if "embedding <->" in sql_str:
            return mock_cursor_vec
        elif "to_tsquery" in sql_str:
            return mock_cursor_bm25
        elif "select text from propositions" in sql_str:
            return mock_cursor_text
        return AsyncMock()

    mock_session.execute = AsyncMock(side_effect=mock_execute)
    
    mock_async_session_instance = MagicMock()
    
    mock_begin_cm = AsyncMock()
    mock_begin_cm.__aenter__.return_value = None
    mock_begin_cm.__aexit__.return_value = None
    mock_async_session_instance.begin.return_value = mock_begin_cm
    
    mock_async_session_instance.execute = mock_session.execute
    
    mock_engine = MagicMock()
    
    with patch("backend.cold_memory.get_engine", return_value=mock_engine), \
         patch("backend.cold_memory.AsyncSession") as MockAsyncSession, \
         patch("backend.cold_memory.httpx.AsyncClient"):
        
        MockAsyncSession.return_value.__aenter__.return_value = mock_async_session_instance
        
        retriever = ColdMemoryRetriever(db_path="", openrouter_api_key="test_key")
        retriever.get_embedding = AsyncMock(return_value=[0.1] * 4096)
        
        results = await retriever.search("test query", user_id="user_123", top_k=5)
        
        assert len(results) == 3
        calls = mock_async_session_instance.execute.call_args_list
        set_config_called = False
        for call in calls:
            sql_str = str(call[0][0])
            if "set_config('request.jwt.claims'" in sql_str:
                set_config_called = True
                assert call[0][1]["uid"] == "user_123"
        assert set_config_called


@pytest.mark.asyncio
async def test_cold_memory_embedding_timeout_returns_no_memory(monkeypatch):
    import backend.cold_memory as cold_memory

    monkeypatch.setattr(cold_memory.settings, "cold_memory_embedding_timeout_ms", 1)
    monkeypatch.setattr(
        cold_memory,
        "_table_availability",
        {"propositions": True, "vec_memory": True},
    )
    retriever = ColdMemoryRetriever(db_path="", openrouter_api_key="test_key")

    async def slow_embedding(_query):
        await asyncio.sleep(0.05)
        return [0.1] * 1536

    retriever.get_embedding = slow_embedding
    trace = MemoryRetrievalTrace(route_reason="SUBSTANTIVE_QUERY")

    with patch("backend.cold_memory.get_engine", return_value=MagicMock()):
        results = await retriever.search(
            "test query",
            user_id="user_123",
            top_k=5,
            memory_trace=trace,
        )

    assert results == []
    assert trace.has_step_outcome("cold_memory_embedding", {"timeout"}) is True
