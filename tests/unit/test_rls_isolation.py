import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from backend.cold_memory import ColdMemoryRetriever

@pytest.mark.asyncio
async def test_rls_isolation_context_injection():
    mock_async_session_instance = MagicMock()
    mock_begin_cm = AsyncMock()
    mock_begin_cm.__aenter__.return_value = None
    mock_begin_cm.__aexit__.return_value = None
    mock_async_session_instance.begin.return_value = mock_begin_cm
    
    async def mock_execute(sql, params=None):
        return MagicMock()

    mock_async_session_instance.execute = AsyncMock(side_effect=mock_execute)
    
    with patch("backend.cold_memory.get_engine"), \
         patch("backend.cold_memory.AsyncSession") as MockAsyncSession:
        
        MockAsyncSession.return_value.__aenter__.return_value = mock_async_session_instance
        
        retriever = ColdMemoryRetriever(db_path="", openrouter_api_key="test_key")
        retriever.get_embedding = AsyncMock(return_value=[0.1] * 1536)
        
        # Search as user A
        await retriever.search("query", user_id="user_A", top_k=5)
        calls = mock_async_session_instance.execute.call_args_list
        rls_call_a = next(c for c in calls if "set_config" in str(c[0][0]))
        assert rls_call_a[0][1]["uid"] == "user_A"
        
        mock_async_session_instance.execute.reset_mock()
        
        # Search as user B
        await retriever.search("query", user_id="user_B", top_k=5)
        calls = mock_async_session_instance.execute.call_args_list
        rls_call_b = next(c for c in calls if "set_config" in str(c[0][0]))
        assert rls_call_b[0][1]["uid"] == "user_B"
