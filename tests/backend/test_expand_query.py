import pytest
from unittest.mock import AsyncMock, MagicMock
from backend.main import expand_query_for_rag

@pytest.mark.asyncio
async def test_expand_query_for_rag():
    mock_client = MagicMock()
    mock_client.chat = MagicMock()
    mock_client.chat.completions = MagicMock()
    mock_client.chat.completions.create = AsyncMock()
    
    # Setup mock response
    mock_chunk = MagicMock()
    # The output format is explicitly requested to not have prefixes, but the regex strips them anyway
    mock_chunk.message.content = "1. First expanded query\n- Second expanded query\nThird expanded query"
    mock_response = MagicMock()
    mock_response.choices = [mock_chunk]
    
    mock_client.chat.completions.create.return_value = mock_response
    
    original_query = "請問賈寶玉是誰？"
    queries = await expand_query_for_rag(original_query, mock_client)
    
    assert len(queries) == 4
    assert queries[0] == "請問賈寶玉是誰？"
    assert queries[1] == "First expanded query"
    assert queries[2] == "Second expanded query"
    assert queries[3] == "Third expanded query"
    
@pytest.mark.asyncio
async def test_expand_query_for_rag_error_fallback():
    mock_client = MagicMock()
    mock_client.chat = MagicMock()
    mock_client.chat.completions = MagicMock()
    mock_client.chat.completions.create = AsyncMock(side_effect=Exception("API Error"))
    
    original_query = "請問賈寶玉是誰？"
    queries = await expand_query_for_rag(original_query, mock_client)
    
    # Should fallback to original query
    assert len(queries) == 1
    assert queries[0] == original_query
